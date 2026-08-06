#!/usr/bin/env python3
"""Run V18-C Eligible Universe engine + write coordinator evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_eligible_universe.evidence import evaluate_lane, write_evidence  # noqa: E402


def _git_head(cwd: Path) -> str:
    return (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(cwd))
        .decode("utf-8")
        .strip()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="V18-C Live Eligible Universe")
    parser.add_argument(
        "--evidence-out",
        default=r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_c_eligible_universe.json",
    )
    parser.add_argument("--skip-live", action="store_true")
    args = parser.parse_args()

    head = _git_head(ROOT)
    evidence = evaluate_lane(head=head, worktree=str(ROOT), try_live=not args.skip_live)
    out = Path(args.evidence_out)
    write_evidence(out, evidence)
    summary = {
        "status": evidence["status"],
        "commit": evidence["commit"],
        "sample_funnel": evidence["sample_funnel"],
        "class_histogram": evidence["fixture_proof"]["class_histogram"],
        "live_ok": evidence["live_catalog_smoke"].get("ok"),
        "evidence_out": str(out),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
