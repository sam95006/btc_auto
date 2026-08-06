#!/usr/bin/env python3
"""Run V17-F Data Trust Engine V2 self-check (stdout only; no status JSON)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_data_trust_engine_v2.engine import evaluate_raw
from backend.nexus_data_trust_engine_v2.fixtures import expected_trust_status, fixture_catalog
from backend.nexus_data_trust_engine_v2.hard_bans import (
    assert_no_status_json_write,
    hard_ban_probe_matrix,
)


def main() -> int:
    for banned in (
        "v17_f_status.json",
        "lane_status.json",
        "data_trust_report.json",
    ):
        try:
            assert_no_status_json_write(banned)
            print(f"ERROR: ban did not fire for {banned}", file=sys.stderr)
            return 2
        except Exception:
            pass

    histogram: dict[str, int] = {}
    failures: list[str] = []
    for case in fixture_catalog():
        result = evaluate_raw(case)
        status = result["trust_status"]
        histogram[status] = histogram.get(status, 0) + 1
        expected = expected_trust_status(case)
        if expected is not None and status != expected:
            failures.append(f"{case['case_id']}: got {status} expected {expected}")

    probes = hard_ban_probe_matrix()
    ok = (not failures) and probes["all_refused"] and probes["env_guard"]["ok"]
    summary = {
        "lane": "V17-F",
        "final_status": "PASS" if ok else "FAIL",
        "fixture_count": len(fixture_catalog()),
        "trust_histogram": histogram,
        "failures": failures,
        "hard_bans_refused": probes["all_refused"],
        "status_json_written": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
