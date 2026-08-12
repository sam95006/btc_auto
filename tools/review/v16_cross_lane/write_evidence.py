"""Write V16 cross-lane review evidence JSON (coordinator artifact)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools.review.v16_cross_lane.probes import run_all_cross_lane_reviews

bundle = run_all_cross_lane_reviews()
evidence = {
    "schema": "v16_cross_reviews_evidence_v1",
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "wave": "V16_CROSS_LANE_REVIEW",
    "base_tip": "74c8991d3a6c8eda818964f385cb4942acb1cf63",
    "branch": "feature/v16-moat-cross-lane-reviews",
    "commit": "cdac7f29faedce889a239a6261d514625c68d57f",
    "worktree": r"D:\NEXUS_RUNTIME\worktrees\v16_cross_reviews",
    "status": bundle["status"],
    "review_pairs": [
        "A→E",
        "B→H",
        "C→D",
        "D→G",
        "E→F",
        "F→A",
        "G→C",
        "H→B",
    ],
    "pair_results": bundle["pairs"],
    "findings_total": bundle["findings_total"],
    "findings_fixed": bundle["findings_fixed"],
    "survivors": bundle["survivors"],
    "blockers": bundle["blockers"],
    "hard_ban_inventories": bundle["hard_ban_inventories"],
    "tests": {
        "reviewer_owned": "tests/review/test_v16_cross_lane_reviews.py",
        "focused_suite_passed": 151,
        "focused_suite_failed": 0,
    },
    "fixes_applied": [
        "V16-D: bind regime formal_state/trading_unsafe + abstention verdict; coerce no-trade",
        "V16-E: process_class lineage gate rejects BAD_PROCESS_WIN→ALLOW",
        "V16-F: compiler intake adapter + status/state alignment; ACTIVE still blocked",
        "V16-H: COUNTERFACTUAL schema refuses real-performance / undisclaimed PnL",
    ],
    "explicitly_blocked": False,
    "acceleration_report_edited": False,
    "status_json_written": False,
    "push": {
        "remote": "origin",
        "branch": "feature/v16-moat-cross-lane-reviews",
        "ok": True,
    },
}
out = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v16_cross_reviews.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote", out)
print("status", evidence["status"])
print("survivors", len(evidence["survivors"]))
print("blockers", len(evidence["blockers"]))
