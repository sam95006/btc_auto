#!/usr/bin/env python3
"""Run V18-D Live Opportunity Pipeline fixture E2E (stdout; no report rewrite)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_live_opportunity_pipeline import run_fixture_e2e
from backend.nexus_live_opportunity_pipeline.hard_bans import hard_ban_probe_matrix


def main() -> int:
    campaign = run_fixture_e2e(force_fixture=True)
    probes = hard_ban_probe_matrix()
    ok = (
        campaign["actual_ordered_count"] == 0
        and campaign["actual_filled_count"] == 0
        and campaign["trade_signal_count"] == 0
        and probes["all_raised"]
        and all(campaign["modules_present"].values())
    )
    summary = {
        "lane": campaign["lane"],
        "final_status": "PASS" if ok else "FAIL",
        "case_count": campaign["case_count"],
        "decision_histogram": campaign["decision_histogram"],
        "decision_enum": campaign["decision_enum"],
        "actual_ordered_count": campaign["actual_ordered_count"],
        "modules_present": campaign["modules_present"],
        "live_hooks_status": campaign["live_hooks"].get("status"),
        "hard_ban_probes": probes,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
