#!/usr/bin/env python3
"""Run V17 deep license enforcement + public inference campaign."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")

from backend.nexus_deep_license_inference.campaign import (  # noqa: E402
    run_campaign,
    write_campaign_artifacts,
)


def main() -> int:
    report = run_campaign()
    path = write_campaign_artifacts(report, root=ROOT)
    print(json.dumps(
        {
            "status": report["status"],
            "survivor_count": report["survivor_count"],
            "attack_count": report["attack_count"],
            "artifact": str(path),
        },
        indent=2,
    ))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
