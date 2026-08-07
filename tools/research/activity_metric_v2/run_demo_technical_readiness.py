#!/usr/bin/env python3
"""DEMO TECHNICAL READINESS — contracts only, demo_order_armed=false, no orders."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_PATH = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_9_demo_technical_readiness.json")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    from backend.nexus_bybit_demo_readiness.gate_v1 import evaluate_demo_readiness

    # Shadow 24h not yet complete at checklist stub time — keep smoke false.
    gate = evaluate_demo_readiness(
        shadow_24h_complete=False,
        shadow_lifecycle_complete=False,
        founder_approval=False,
    )

    # Explicit checklist dimensions required by task.
    checklist = {
        "idempotency": {
            "contract": "order_idempotency_client_order_id_duplicate_prevention",
            "passed": any(
                c["gate_id"] == "order_idempotency_client_order_id_duplicate_prevention" and c["passed"]
                for c in gate["checks"]
            ),
        },
        "reconciliation": {
            "contract": "reconciliation_restart_recovery",
            "passed": any(
                c["gate_id"] == "reconciliation_restart_recovery" and c["passed"]
                for c in gate["checks"]
            ),
        },
        "reduce_only": {
            "contract": "reduce_only_sl_tp_cancel_contracts",
            "passed": any(
                c["gate_id"] == "reduce_only_sl_tp_cancel_contracts" and c["passed"]
                for c in gate["checks"]
            ),
        },
        "kill_switch": {
            "contract": "kill_switch_max_positions_notional_simulated_risk",
            "passed": any(
                c["gate_id"] == "kill_switch_max_positions_notional_simulated_risk" and c["passed"]
                for c in gate["checks"]
            ),
        },
    }

    report = {
        "schema": "v18_2_9_demo_technical_readiness_v1",
        "generated_at": _utc(),
        "demo_order_armed": False,
        "autonomous_demo_order_allowed": False,
        "orders_executed": False,
        "exchange_write_attempt": 0,
        "mainnet_client": 0,
        "real_money": False,
        "checklist": checklist,
        "checklist_all_passed": all(v["passed"] for v in checklist.values()),
        "gate": gate,
        "status": gate.get("status"),
        "technical_smoke_ready": False,
        "note": (
            "Contract validation only. demo_order_armed must remain false. "
            "Continue idempotency/reconciliation/reduce-only/kill-switch readiness only. "
            "No Demo/mainnet orders placed."
        ),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT_PATH), "demo_order_armed": False, "checklist": checklist}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
