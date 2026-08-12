#!/usr/bin/env python3
"""CLI: run FOUNDER R1 Decision + Execution review (two passes) and write artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.review.r1_decision_execution.runner import ARTIFACT_DIR, run_r1_review, write_artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FOUNDER R1 Decision+Execution review")
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--out", type=Path, default=ARTIFACT_DIR)
    args = parser.parse_args(argv)
    report = run_r1_review(passes=args.passes)
    paths = write_artifacts(args.out, report=report)
    matrix = report["summary"]
    print(json.dumps(
        {
            "false_PASS_count": matrix["false_PASS_count"],
            "authority_conflict_count": matrix["authority_conflict_count"],
            "missing_negative_test_count": matrix["missing_negative_test_count"],
            "critical_findings": [c.get("id") for c in matrix["critical_findings"]],
            "high_findings": [h.get("id") for h in matrix["high_findings"]],
            "integration_recommendation": matrix["integration_recommendation"],
            "artifacts": {k: str(v) for k, v in paths.items()},
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
