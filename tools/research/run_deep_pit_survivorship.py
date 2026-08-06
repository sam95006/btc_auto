#!/usr/bin/env python3
"""Run V17 deep PIT / survivorship / symbol-collision campaign + evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_deep_pit_survivorship.constants import EVIDENCE_PATH  # noqa: E402
from backend.nexus_deep_pit_survivorship.evidence import build_evidence, write_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--evidence", type=Path, default=Path(EVIDENCE_PATH))
    parser.add_argument(
        "--tests-json",
        type=Path,
        default=None,
        help="Optional pytest summary JSON to embed",
    )
    args = parser.parse_args()
    tests = None
    if args.tests_json and args.tests_json.is_file():
        tests = json.loads(args.tests_json.read_text(encoding="utf-8"))
    evidence = build_evidence(repo_root=args.repo_root, tests=tests)
    written = write_evidence(evidence, path=args.evidence)
    print(
        json.dumps(
            {
                "status": written["status"],
                "HEAD": written["HEAD"],
                "survivor_count": written["survivor_count"],
                "survivors": written["survivors"],
                "attack_count": written["attack_count"],
                "evidence": str(args.evidence),
            },
            indent=2,
        )
    )
    return 0 if written.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
