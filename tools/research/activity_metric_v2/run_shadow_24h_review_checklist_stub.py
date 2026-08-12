#!/usr/bin/env python3
"""24H Shadow review checklist stub — Coordinator fills at target_end. Do NOT claim PASS."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

OUT_PATH = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_9_shadow_24h_review_checklist.json")

TARGET_END = "2026-08-07T06:35:07Z"
CAMPAIGN_ID = "shadow_24h_20260806T063504Z"
START = "2026-08-06T06:35:07Z"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    now = datetime.now(timezone.utc)
    target = datetime.fromisoformat(TARGET_END.replace("Z", "+00:00"))
    before_target = now < target

    report = {
        "schema": "v18_2_9_shadow_24h_review_checklist_v1",
        "generated_at": _utc(),
        "campaign_id": CAMPAIGN_ID,
        "start": START,
        "target_end": TARGET_END,
        "status": "CHECKLIST_STUB_AWAITING_COORDINATOR",
        "claim_pass": False,
        "pass": False,
        "operational_continuity_pass": None,
        "strategy_qualification_pass": None,
        "before_target_end": before_target,
        "coordinator_fill_required": True,
        "pid_do_not_restart": 18992,
        "checklist_items": [
            {
                "id": "duration_reached",
                "question": "Has target_end 2026-08-07T06:35:07Z been reached?",
                "value": None,
                "filled_by": None,
            },
            {
                "id": "pid_alive",
                "question": "Is campaign PID 18992 still alive (do not restart/stop)?",
                "value": None,
                "filled_by": None,
            },
            {
                "id": "heartbeat_fresh",
                "question": "Is heartbeat fresh within campaign SLO?",
                "value": None,
                "filled_by": None,
            },
            {
                "id": "no_exchange_writes",
                "question": "exchange_write_attempt == 0 and demo/mainnet orders == 0?",
                "value": None,
                "filled_by": None,
            },
            {
                "id": "eligible_universe",
                "question": "eligible count and primary block reasons at target_end?",
                "value": None,
                "filled_by": None,
            },
            {
                "id": "activity_metric_gap",
                "question": "Is trade_count_24h still unavailable / Activity Metric V2 proxy wired?",
                "value": None,
                "filled_by": None,
            },
            {
                "id": "qualification_ready_count",
                "question": "qualification_ready_count at review (expect 0 unless Formal WF authorized)?",
                "value": None,
                "filled_by": None,
            },
            {
                "id": "formal_wf_oos",
                "question": "Formal WF executed? OOS consumed? (default false/false)",
                "value": None,
                "filled_by": None,
            },
            {
                "id": "runtime_restarts",
                "question": "runtime_restart_count and data_class at target_end?",
                "value": None,
                "filled_by": None,
            },
            {
                "id": "overall_verdict",
                "question": "Coordinator overall verdict (do not claim PASS in stub)",
                "value": None,
                "filled_by": None,
            },
        ],
        "hard_bans": [
            "do_not_modify_running_shadow_campaign_files",
            "do_not_restart_or_stop_pid_18992",
            "do_not_claim_pass_in_stub",
            "do_not_arm_demo_orders",
        ],
        "note": (
            "Stub only. Coordinator fills at/after target_end. "
            "Operational review ≠ Formal WF / OOS / Demo arm. Do not claim PASS."
        ),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT_PATH), "claim_pass": False, "status": report["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
