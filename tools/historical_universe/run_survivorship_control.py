#!/usr/bin/env python3
"""V17-E Historical Universe / Survivorship Control runner."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_historical_universe.evidence import (  # noqa: E402
    evaluate_lane,
    write_evidence_coordinator,
    write_immutable_artifacts,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V17-E survivorship control")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Worktree / repo root",
    )
    parser.add_argument(
        "--evidence-path",
        type=Path,
        default=None,
        help="Evidence coordinator JSON path",
    )
    parser.add_argument(
        "--skip-artifacts",
        action="store_true",
        help="Skip immutable artifact write",
    )
    args = parser.parse_args(argv)

    evidence = evaluate_lane(repo_root=args.repo_root)
    if not args.skip_artifacts:
        write_immutable_artifacts(evidence, repo_root=args.repo_root)
    out = write_evidence_coordinator(evidence, path=args.evidence_path)
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "passed": evidence["passed"],
                "commit": evidence["commit"],
                "survivors": evidence["survivors"],
                "fixture_pass_count": evidence["fixture_pass_count"],
                "attack_blocked_count": evidence["attack_blocked_count"],
                "evidence_path": str(out),
                "recommendation": evidence["recommendation"],
            },
            indent=2,
        )
    )
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
