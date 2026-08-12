#!/usr/bin/env python3
"""V16-F Lesson Validation Firewall harness.

THREE PASSES. Interfaces / fixtures / safety gates only.
NEVER marks real Lesson ACTIVE. Does NOT write status JSON or reports.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")
os.environ.setdefault("OOS_EXECUTE", "false")
os.environ.setdefault("FORMAL_WF_EXECUTE", "false")

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_lesson_validation_firewall.bans import (  # noqa: E402
    HardBanViolation,
    assert_no_status_json_filenames,
    refuse_status_json_report,
)
from backend.nexus_lesson_validation_firewall.constants import (  # noqa: E402
    FORBIDDEN_STATUS_BASENAMES,
    LANE,
)
from backend.nexus_lesson_validation_firewall.firewall import (  # noqa: E402
    run_three_pass,
    summarize_for_return,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V16-F Lesson Validation Firewall (three-pass)")
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Print compact in-memory summary to stdout (never writes status/report files).",
    )
    parser.add_argument(
        "--write-status",
        action="store_true",
        help="Adversarial: attempt status write (must refuse).",
    )
    args = parser.parse_args(argv)

    if args.write_status:
        refusal = refuse_status_json_report("v16_f_status.json")
        print(json.dumps({"lane": LANE, "refusal": refusal}, indent=2))
        return 2 if refusal.get("allowed") else 0

    result = run_three_pass()
    # Prove we did not produce forbidden artifact names.
    assert_no_status_json_filenames([])
    for name in FORBIDDEN_STATUS_BASENAMES:
        try:
            assert_no_status_json_filenames([f"artifacts/tmp/{name}"])
            raise HardBanViolation(f"expected_ban_missed:{name}")
        except HardBanViolation:
            pass

    summary = summarize_for_return(result)
    if args.print_summary:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        # Minimal stdout for CI — not a status/report artifact file.
        print(
            f"{LANE} three_pass={'PASS' if summary['status'] == 'PASS' else 'FAIL'} "
            f"real_active=False blockers={len(summary['blockers'])}"
        )
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
