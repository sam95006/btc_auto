#!/usr/bin/env python3
"""Run V18-B Incremental Backfill + Live Ingest campaign."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_incremental_backfill_live_ingest.campaign import run_campaign  # noqa: E402


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
        )
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def main() -> int:
    head = _git_head()
    report = run_campaign(ROOT, head=head)
    print(
        json.dumps(
            {
                "status": report["status"],
                "HEAD": report["HEAD"],
                "acceptance_zeros": report["acceptance_zeros"],
                "classification_counts": report.get("classification_counts"),
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
