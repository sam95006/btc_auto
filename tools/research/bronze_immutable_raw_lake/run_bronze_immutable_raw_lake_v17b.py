#!/usr/bin/env python3
"""Run V17-B Bronze Immutable Raw Data Lake campaign (bounded fixture round)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_bronze_immutable_raw_lake.campaign import run_campaign  # noqa: E402


def main() -> int:
    report = run_campaign(ROOT)
    print(json.dumps({"status": report["status"], "real_or_fixture": report["real_or_fixture"]}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
