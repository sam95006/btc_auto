#!/usr/bin/env python3
"""Run Autonomous Closed-Loop Harness V1 and write immutable package."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/readiness/immutable/autonomous_closed_loop_harness_v1"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def main() -> int:
    from backend.nexus_autonomy.closed_loop_harness_v1 import STATES, ALLOWED, run_harness

    result = run_harness()
    OUT.mkdir(parents=True, exist_ok=True)
    _write(
        OUT / "state_machine_contract.json",
        {"states": list(STATES), "allowed_transitions": [list(x) for x in sorted(ALLOWED)], "fail_closed": True},
    )
    _write(OUT / "scenario_matrix_result.json", result)
    _write(
        OUT / "idempotency_result.json",
        {"status": result.get("duplicate_intent_idempotency_status"), "created_at": _utc()},
    )
    _write(
        OUT / "risk_override_result.json",
        {"status": result.get("hard_risk_override_status"), "created_at": _utc()},
    )
    _write(
        OUT / "restart_recovery_result.json",
        {"status": result.get("restart_recovery_status"), "created_at": _utc()},
    )
    _write(OUT / "closed_loop_harness_status.json", result)
    print(json.dumps({"recommendation": result.get("recommendation"), **{k: result.get(k) for k in [
        "scenario_count","scenario_pass_count","scenario_failure_count","exchange_write_attempt_count","demo_order_count","real_learning_claimed"
    ]}}, indent=2))
    return 0 if result.get("recommendation") == "NEXUS_AUTONOMOUS_HARNESS_V1_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
