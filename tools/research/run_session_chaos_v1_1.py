#!/usr/bin/env python3
"""Run NEXUS Autonomous Session Orchestrator V1.1 chaos campaign → immutable package."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/readiness/immutable/autonomous_session_orchestrator_v1_1"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from backend.nexus_autonomy.session_chaos_recovery_v1_1 import (
        FROZEN_SEED,
        PASS_STATUS,
        run_session_chaos_campaign,
    )

    run_root = ROOT / ".nexus_runtime" / "tmp" / "session_chaos_v1_1"
    run_root.mkdir(parents=True, exist_ok=True)
    print(f"session chaos campaign root={run_root}", flush=True)
    package = run_session_chaos_campaign(run_root, seed=FROZEN_SEED)

    status = {
        "schema": "autonomous_session_orchestrator_v1_1",
        "package": "NEXUS_AUTONOMOUS_SESSION_ORCHESTRATOR_V1_1",
        "Session_Chaos_status": package.get("Session_Chaos_status"),
        "seed": package.get("seed"),
        "logical_sessions_hours": package.get("logical_sessions_hours"),
        "chaos_catalog": package.get("chaos_catalog"),
        "metrics_summary": package.get("metrics_summary"),
        "invariants": package.get("invariants"),
        "exchange_write_attempt_count": package.get("exchange_write_attempt_count"),
        "sessions": {
            k: {
                "session_id": v.get("session_id"),
                "logical_duration_hours": v.get("logical_duration_hours"),
                "final_state": v.get("final_state"),
                "session_pass": v.get("session_pass"),
                "invariants_status": v.get("invariants_status"),
                "invariants_counts": v.get("invariants_counts"),
                "metrics": v.get("metrics"),
                "checkpoint_count": v.get("checkpoint_count"),
                "restart_count": v.get("restart_count"),
                "recovery_count": v.get("recovery_count"),
                "kill_switch_status": v.get("kill_switch_status"),
                "exchange_write_attempt_count": v.get("exchange_write_attempt_count"),
            }
            for k, v in (package.get("sessions") or {}).items()
        },
        "mode": package.get("mode"),
        "created_at": _utc(),
    }
    _write(OUT / "session_chaos_status.json", status)
    _write(OUT / "metrics_summary.json", package.get("metrics_summary") or {})
    _write(OUT / "invariants.json", package.get("invariants") or {})
    _write(
        OUT / "chaos_catalog.json",
        {
            "catalog": package.get("chaos_catalog"),
            "seed": package.get("seed"),
            "created_at": _utc(),
        },
    )

    print(
        json.dumps(
            {
                "Session_Chaos_status": status["Session_Chaos_status"],
                "metrics_summary": status["metrics_summary"],
                "invariants": status["invariants"],
                "out": str(OUT),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if status["Session_Chaos_status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
