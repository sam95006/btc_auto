"""BYBIT_DEMO_READINESS_GATE_V1 evaluator — Founder-only, non-mutating."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_bybit_demo_readiness.contracts import ALL_HARNESS_CHECKS, GateCheckResult

DEMO_STATES = (
    "DEMO_NOT_READY",
    "DEMO_TECHNICAL_SMOKE_READY",
    "DEMO_AUTONOMOUS_STRATEGY_READY",
)

GATE_SCHEMA = "bybit_demo_readiness_gate_v1"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class BybitDemoReadinessGateV1:
    """Founder-only Demo readiness gate.

    Hard rules this round:
    - autonomous_demo_order_allowed = False always
    - demo_order_armed = False
    - founder_approval_required = True
    - NEVER mark DEMO_AUTONOMOUS_STRATEGY_READY
    - technical_smoke_ready stays False until shadow lifecycle gates met
      (harness_tests_pass may be True independently)
    """

    shadow_24h_complete: bool = False
    shadow_lifecycle_complete: bool = False
    founder_approval: bool = False
    demo_order_armed: bool = False  # MUST remain False this round
    checks: list[GateCheckResult] = field(default_factory=list)

    def run_harness_checks(self) -> list[GateCheckResult]:
        self.checks = [fn() for fn in ALL_HARNESS_CHECKS]
        return self.checks

    def evaluate(self) -> dict[str, Any]:
        if not self.checks:
            self.run_harness_checks()

        failed = [c for c in self.checks if not c.passed]
        harness_tests_pass = len(failed) == 0

        missing_gates: list[str] = []
        if not harness_tests_pass:
            missing_gates.extend(f"harness:{c.gate_id}" for c in failed)
        if not self.shadow_24h_complete:
            missing_gates.append("shadow_24h_qualification_incomplete")
        if not self.shadow_lifecycle_complete:
            missing_gates.append("shadow_lifecycle_incomplete")
        if not self.founder_approval:
            missing_gates.append("founder_approval_required")
        # Always list armed=false as intentional gate (not a failure of harness).
        if self.demo_order_armed:
            # Safety: force false path — if somehow True, treat as blocker.
            missing_gates.append("demo_order_armed_must_be_false")

        # Prefer DEMO_NOT_READY while shadow gates unmet even if harness passes.
        technical_smoke_ready = False
        status = "DEMO_NOT_READY"
        if harness_tests_pass and self.shadow_24h_complete and self.shadow_lifecycle_complete:
            # Still require founder approval + armed=false for technical smoke.
            if self.founder_approval and not self.demo_order_armed:
                technical_smoke_ready = True
                status = "DEMO_TECHNICAL_SMOKE_READY"
            else:
                status = "DEMO_NOT_READY"
                if "founder_approval_required" not in missing_gates:
                    missing_gates.append("founder_approval_required")
        else:
            status = "DEMO_NOT_READY"

        # NEVER promote autonomous this round.
        autonomous_demo_ready = False
        autonomous_demo_order_allowed = False

        return {
            "schema": GATE_SCHEMA,
            "status": status,
            "technical_smoke_ready": technical_smoke_ready,
            "harness_tests_pass": harness_tests_pass,
            "autonomous_demo_ready": autonomous_demo_ready,
            "autonomous_demo_order_allowed": autonomous_demo_order_allowed,
            "demo_order_armed": False,
            "founder_approval_required": True,
            "founder_approval_granted": bool(self.founder_approval),
            "missing_gates": missing_gates,
            "shadow_24h_complete": bool(self.shadow_24h_complete),
            "shadow_lifecycle_complete": bool(self.shadow_lifecycle_complete),
            "checks": [c.to_dict() for c in self.checks],
            "isolation": {
                "public": False,
                "member": False,
                "founder_only": True,
            },
            "safety": {
                "exchange_write_attempt_count": 0,
                "mainnet_client_count": 0,
                "demo_order_count": 0,
                "real_money": False,
                "orders_executed": False,
            },
            "evaluated_at": _utc(),
            "note": (
                "Prep-only. Command scaffolding present but must not execute. "
                "DEMO_AUTONOMOUS_STRATEGY_READY forbidden this round. "
                "technical_smoke_ready remains false until shadow gates met (directive 8.1)."
            ),
        }


def evaluate_demo_readiness(
    *,
    shadow_24h_complete: bool = False,
    shadow_lifecycle_complete: bool = False,
    founder_approval: bool = False,
) -> dict[str, Any]:
    gate = BybitDemoReadinessGateV1(
        shadow_24h_complete=shadow_24h_complete,
        shadow_lifecycle_complete=shadow_lifecycle_complete,
        founder_approval=founder_approval,
        demo_order_armed=False,
    )
    return gate.evaluate()


def write_evidence(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
