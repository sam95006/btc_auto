#!/usr/bin/env python3
"""Close orphaned Bybit demo open position (Stage 3 manual recovery only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_client import BybitDemoClient  # noqa: E402


def main() -> int:
    client = BybitDemoClient("demo-order", allow_demo_order=True)
    before = client.count_open_positions()
    result = {"open_positions_before": before}
    if before > 0:
        result["close"] = client.close_demo_position_market()
    result["open_positions_after"] = client.count_open_positions()
    print(json.dumps(result, indent=2))
    return 0 if result["open_positions_after"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
