"""Demo execution safety gate — staged enablement with fail-closed defaults."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_demo_execution import BYBIT_DEMO, DEMO_EXECUTION_LABELS, MAINNET, REAL_MONEY


class SafetyGateStage(str, Enum):
    READ_ONLY = "READ_ONLY"
    ACCOUNT_RECONCILED = "ACCOUNT_RECONCILED"
    DRY_RUN_INTENT = "DRY_RUN_INTENT"
    DEMO_ORDER_SMOKE = "DEMO_ORDER_SMOKE"
    PROTECTION_VERIFIED = "PROTECTION_VERIFIED"
    FOUNDER_CONFIRMATION = "FOUNDER_CONFIRMATION"
    DEMO_AUTONOMOUS_ENABLED = "DEMO_AUTONOMOUS_ENABLED"


class AutonomousMode(str, Enum):
    DEMO_AUTONOMOUS_DISABLED = "DEMO_AUTONOMOUS_DISABLED"
    DEMO_AUTONOMOUS_ENABLED = "DEMO_AUTONOMOUS_ENABLED"


STAGE_ORDER: tuple[SafetyGateStage, ...] = (
    SafetyGateStage.READ_ONLY,
    SafetyGateStage.ACCOUNT_RECONCILED,
    SafetyGateStage.DRY_RUN_INTENT,
    SafetyGateStage.DEMO_ORDER_SMOKE,
    SafetyGateStage.PROTECTION_VERIFIED,
    SafetyGateStage.FOUNDER_CONFIRMATION,
    SafetyGateStage.DEMO_AUTONOMOUS_ENABLED,
)

NEXT_GATE_AFTER_SMOKE = SafetyGateStage.FOUNDER_CONFIRMATION


@dataclass
class GateTransition:
    stage: SafetyGateStage
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage.value, "passed": self.passed, "detail": self.detail}


@dataclass
class DemoExecutionSafetyGate:
    """Any failure forces DEMO_AUTONOMOUS_DISABLED."""

    current_stage: SafetyGateStage = SafetyGateStage.READ_ONLY
    autonomous_mode: AutonomousMode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
    transitions: list[GateTransition] = field(default_factory=list)
    last_failure: str = ""

    def reset(self) -> None:
        self.current_stage = SafetyGateStage.READ_ONLY
        self.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
        self.transitions.clear()
        self.last_failure = ""

    def fail(self, detail: str) -> None:
        self.last_failure = detail
        self.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
        self.transitions.append(
            GateTransition(stage=self.current_stage, passed=False, detail=detail)
        )

    def advance(self, stage: SafetyGateStage, *, detail: str = "") -> bool:
        expected_idx = STAGE_ORDER.index(self.current_stage)
        target_idx = STAGE_ORDER.index(stage)
        if target_idx != expected_idx + 1 and target_idx > expected_idx:
            self.fail(f"stage_skip_forbidden:{self.current_stage.value}->{stage.value}")
            return False
        if not BYBIT_DEMO or MAINNET or REAL_MONEY:
            self.fail("demo_only_boundary_violation")
            return False
        self.current_stage = stage
        self.transitions.append(GateTransition(stage=stage, passed=True, detail=detail))
        if stage == SafetyGateStage.DEMO_AUTONOMOUS_ENABLED:
            self.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_ENABLED
        else:
            self.autonomous_mode = AutonomousMode.DEMO_AUTONOMOUS_DISABLED
        return True

    def can_write_orders(self) -> bool:
        idx = STAGE_ORDER.index(self.current_stage)
        smoke_idx = STAGE_ORDER.index(SafetyGateStage.DEMO_ORDER_SMOKE)
        return (
            idx >= smoke_idx
            and self.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_ENABLED
            and not self.last_failure
        )

    @property
    def first_demo_smoke_order_ready(self) -> bool:
        idx = STAGE_ORDER.index(self.current_stage)
        smoke_idx = STAGE_ORDER.index(SafetyGateStage.DEMO_ORDER_SMOKE)
        return idx >= smoke_idx and not self.last_failure

    @property
    def next_gate(self) -> str:
        if self.last_failure:
            return "RECOVERY_REQUIRED"
        idx = STAGE_ORDER.index(self.current_stage)
        if idx >= len(STAGE_ORDER) - 1:
            return "NONE"
        if self.current_stage == SafetyGateStage.PROTECTION_VERIFIED:
            return "FOUNDER_CONFIRMATION_AFTER_SMOKE"
        return STAGE_ORDER[idx + 1].value

    def snapshot(self) -> dict[str, Any]:
        return {
            "current_stage": self.current_stage.value,
            "autonomous_mode": self.autonomous_mode.value,
            "next_gate": self.next_gate,
            "first_demo_smoke_order_ready": self.first_demo_smoke_order_ready,
            "can_write_orders": self.can_write_orders(),
            "last_failure": self.last_failure,
            "labels": list(DEMO_EXECUTION_LABELS),
            "transitions": [t.to_dict() for t in self.transitions],
        }
