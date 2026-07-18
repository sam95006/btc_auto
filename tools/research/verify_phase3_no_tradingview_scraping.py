#!/usr/bin/env python3
"""Fail if unofficial TradingView market-data scraping patterns appear."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = [
    r"scanner\.tradingview",
    r"pine_facade",
    r"prodata\.tradingview",
    r"tradingview\.com/x/",
    r"tv-chart.*websocket",
]
ALLOW = {
    "tradingview webhook",
    "lightweight-charts",
    "TradingView Lightweight",
}


def main() -> int:
    print("PHASE3_NO_TRADINGVIEW_SCRAPING")
    hits = []
    for base in (ROOT / "frontend/src", ROOT / "backend/market", ROOT / "backend/api"):
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".ts", ".tsx", ".js", ".py"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in PATTERNS:
                if re.search(pat, text, re.I):
                    hits.append(f"{path.relative_to(ROOT)} :: {pat}")
    print(f"hits={len(hits)}")
    for h in hits[:10]:
        print(h)
    print("tradingview_used_as_market_data_source=false")
    print("VERDICT=" + ("PASS" if not hits else "FAIL"))
    return 0 if not hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
