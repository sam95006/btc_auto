#!/usr/bin/env python3
"""V15-A Real Historical Development Data Foundation campaign runner.

Read-only PIT development dataset foundation from in-repo public/sanitized
historical sources and documented read-only public endpoints.

Hard bans: no PR26/27 merge, deploy, WF, OOS exec/consume, Demo, exchange write,
mainnet, fabricated edge, invented history.

Does NOT emit human-facing v15_*_status.json — stdout + immutable campaign artifacts only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_dev_data_foundation.campaign import run_campaign  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="V15-A PIT development data foundation (two-pass)")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    campaign = run_campaign(args.root.resolve(), run_tests=not args.skip_tests)
    # Structured stdout for coordinator merge (no v15_*_status.json)
    print(json.dumps(campaign, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if campaign.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
