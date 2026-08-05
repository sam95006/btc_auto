"""NEXUS V10 Execution Session Scale — public facade (Lane B).

Orchestrates:
  * 100,000 deterministic execution fuzz scenarios
  * readiness artifact packaging for the scale lane

Canonical execution authority remains:
  backend.nexus_execution.execution_simulator_v1_1.AutonomousExecutionSimulatorV11
routed via NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1.

Execution mode: SIMULATED_NO_EXCHANGE_WRITE.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import backend.nexus_execution.security_boundary as security_boundary
from backend.nexus_execution.orchestrator_adapter_v1 import (
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    CANONICAL_EXECUTION_ENGINE_COUNT,
)
from backend.nexus_execution.scale_.config import (
    DEFAULT_FUZZ_SCENARIOS,
    ScaleConfig,
    load_scale_config,
)
from backend.nexus_execution.scale_.fuzz_scale import (
    fuzz_scale_summary,
    run_execution_fuzz_scale,
)
from backend.nexus_execution.scale_.injections import injection_matrix

SCALE_SCHEMA = "v10_execution_session_scale"
SCALE_PACKAGE = "NEXUS_V10_EXECUTION_SESSION_SCALE"
PASS_STATUS = "NEXUS_V10_EXECUTION_SESSION_SCALE_PASS"
INVALID_PREFIX = "NEXUS_V10_EXECUTION_SESSION_SCALE_INVALID"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_scale_fuzz(*, config: ScaleConfig | None = None) -> dict[str, Any]:
    """Run the execution fuzz scale campaign and return a JSON-ready report."""
    security_boundary.reset_counters()
    cfg = config or load_scale_config()
    report = run_execution_fuzz_scale(config=cfg)
    summary = fuzz_scale_summary(report, config=cfg)
    summary["recommendation"] = (
        PASS_STATUS
        if summary["pass"]
        else f"{INVALID_PREFIX}:FUZZ_INVARIANTS"
    )
    summary["scenario_breakdown"] = report.scenario_breakdown
    return summary


def write_scale_artifacts(
    out_dir: Path,
    *,
    fuzz: dict[str, Any],
    session: dict[str, Any] | None = None,
    secret_scan: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Persist immutable readiness artifacts under ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def _write(name: str, obj: object) -> Path:
        path = out_dir / name
        path.write_text(
            json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        paths[name] = path
        return path

    _write("fuzz_summary.json", fuzz)
    _write("injection_matrix.json", injection_matrix())
    if session is not None:
        _write("session_scale_report.json", session)
    if secret_scan is not None:
        _write("secret_scan.json", secret_scan)

    fuzz_pass = bool(fuzz.get("pass"))
    session_pass = True if session is None else bool(session.get("session_scale_pass"))
    secret_pass = True if secret_scan is None else int(secret_scan.get("secret_leak_count", 0)) == 0
    all_pass = fuzz_pass and session_pass and secret_pass and fuzz.get("exchange_write_attempt_count", 1) == 0

    status = {
        "schema": SCALE_SCHEMA,
        "package": SCALE_PACKAGE,
        "status": PASS_STATUS if all_pass else f"{INVALID_PREFIX}:AGGREGATE",
        "adapter_id": ADAPTER_ID,
        "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
        "canonical_execution_engine_count": CANONICAL_EXECUTION_ENGINE_COUNT,
        "fuzz_scenarios_achieved": fuzz.get("generated_execution_scenario_count"),
        "fuzz_scenarios_target": fuzz.get("target_scenarios", DEFAULT_FUZZ_SCENARIOS),
        "fuzz_pass": fuzz_pass,
        "session_scale_pass": session_pass,
        "secret_scan_pass": secret_pass,
        "exchange_write_attempt_count": fuzz.get("exchange_write_attempt_count", 0),
        "demo_order_count": fuzz.get("demo_order_count", 0),
        "mainnet": False,
        "real_money": False,
        "mode": "SIMULATED_NO_EXCHANGE_WRITE",
        "created_at": _utc(),
    }
    _write("scale_status.json", status)

    readiness = {
        "schema": f"{SCALE_SCHEMA}_readiness",
        "package": SCALE_PACKAGE,
        "recommendation": status["status"],
        "fuzz": {
            "generated_execution_scenario_count": fuzz.get("generated_execution_scenario_count"),
            "target_scenarios": fuzz.get("target_scenarios"),
            "invariants": fuzz.get("invariants"),
            "pass": fuzz_pass,
        },
        "session": None
        if session is None
        else {
            "session_scale_pass": session.get("session_scale_pass"),
            "logical_sessions_hours": session.get("logical_sessions_hours"),
            "sessions": {
                k: {
                    "final_state": v.get("final_state"),
                    "session_pass": v.get("session_pass"),
                    "logical_duration_hours": v.get("logical_duration_hours"),
                }
                for k, v in (session.get("sessions") or {}).items()
            },
            "focused_probes": session.get("focused_probes"),
        },
        "secret_scan": secret_scan,
        "exchange_write_attempt_count": status["exchange_write_attempt_count"],
        "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
        "adapter_id": ADAPTER_ID,
        "generated_at": _utc(),
    }
    _write("readiness_report.json", readiness)
    return paths


__all__ = [
    "INVALID_PREFIX",
    "PASS_STATUS",
    "SCALE_PACKAGE",
    "SCALE_SCHEMA",
    "run_scale_fuzz",
    "write_scale_artifacts",
]
