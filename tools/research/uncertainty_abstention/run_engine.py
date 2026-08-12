#!/usr/bin/env python3
"""Run V16-G three-pass uncertainty/abstention campaign (stdout only; no status JSON)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_uncertainty_abstention.hard_bans import assert_no_status_json_write
from backend.nexus_uncertainty_abstention.three_pass import run_three_passes


def main() -> int:
    # Explicit hard ban: refuse any accidental status artifact path.
    for banned in (
        "v16_g_status.json",
        "lane_status.json",
        "uncertainty_abstention_report.json",
    ):
        try:
            assert_no_status_json_write(banned)
            print(f"ERROR: ban did not fire for {banned}", file=sys.stderr)
            return 2
        except Exception:
            pass

    result = run_three_passes(repo_root=ROOT)
    # Print compact summary only — never write *_status.json / *_report.json.
    summary = {
        "lane": result["lane"],
        "final_status": result["final_status"],
        "pass_count": result["pass_count"],
        "all_passes_ok": result["all_passes_ok"],
        "deterministic": result["deterministic"],
        "code_checksum": result["code_checksum"],
        "verdict_histogram": result["passes"][-1]["verdict_histogram"],
        "fail_open_blocked": result["passes"][-1]["fail_open_review"]["all_fail_open_blocked"],
        "status_json_written": result["status_json_written"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if result["final_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
