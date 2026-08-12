#!/usr/bin/env python3
"""Print V18-A acceptance summary (fixture mode)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_official_market_adapters.registry import OfficialMarketAdapterRegistry


def main() -> int:
    reg = OfficialMarketAdapterRegistry(use_fixtures=True)
    summary = reg.evidence_summary()
    print(json.dumps(summary, indent=2))
    return 0 if summary["acceptance_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
