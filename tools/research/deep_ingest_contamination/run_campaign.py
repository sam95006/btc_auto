#!/usr/bin/env python3
"""Runner for V17 deep ingest recovery + dataset contamination.

Fixture-only. MUST NOT: exchange write, mainnet, formal WF, OOS, report edit, PR26/27.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_deep_ingest_contamination.campaign import run_campaign  # noqa: E402


def _git_head(root: Path) -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                stderr=subprocess.DEVNULL,
            )
            .decode("utf-8")
            .strip()
        )
    except Exception:
        return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser(description="V17 deep ingest contamination campaign")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    head = _git_head(args.root)
    report = run_campaign(root=args.root, head=head)
    print(json.dumps(
        {
            "status": report["status"],
            "HEAD": report["HEAD"],
            "survivor_count": report["survivor_count"],
            "survivors": report["survivors"],
            "coverage": report["coverage"],
            "artifact_dir": report.get("artifact_dir"),
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
