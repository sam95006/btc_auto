#!/usr/bin/env python3
"""MVP-22A Live Market Data Truth Layer safety + structure checks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"

REQUIRED_FILES = [
    "market/types.ts",
    "market/freshness.ts",
    "market/bybitPublicRest.ts",
    "market/bybitPublicWs.ts",
    "market/LiveMarketFeed.ts",
    "market/useLiveMarketFeed.tsx",
    "components/MarketTopTicker.tsx",
    "components/SimplifiedMarketDashboard.tsx",
]

REQUIRED_STRINGS = [
    "BYBIT_MAINNET_LINEAR",
    "lastPrice",
    "REST_FALLBACK",
    "LiveMarketProvider",
    "Signal Reference Price",
    "NEXUS_UI_MVP22A_LIVE_MARKET_DATA",
    "NEXUS — Live Market Intelligence",
]

FORBIDDEN = [
    (r"api\.bybit\.com.*(order|position|account|wallet)", "private_bybit_path"),
    (r"\bStart Stage 4\.?19\b", "start_stage_419"),
    (r"\bQuick Order\b", "quick_order"),
    (r'path:\s*["\']/trade', "trade_route"),
]


def main() -> int:
    issues: list[str] = []
    for rel in REQUIRED_FILES:
        if not (FRONTEND_SRC / rel).is_file():
            issues.append(f"missing:{rel}")

    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in FRONTEND_SRC.rglob("*")
        if p.suffix in {".ts", ".tsx", ".css", ".html"} and p.is_file()
    )
    # also index.html at frontend root
    index = ROOT / "frontend" / "index.html"
    if index.is_file():
        blob += "\n" + index.read_text(encoding="utf-8", errors="replace")

    for s in REQUIRED_STRINGS:
        if s not in blob:
            issues.append(f"missing_string:{s}")

    for pat, name in FORBIDDEN:
        if re.search(pat, blob, re.I):
            # allow documentation negatives
            if name in {"start_stage_419", "quick_order"} and re.search(
                rf"(no|never|forbidden).{{0,40}}{pat}", blob, re.I
            ):
                continue
            issues.append(f"forbidden:{name}")

    market_py = ROOT / "backend" / "api" / "market_public_routes.py"
    if not market_py.is_file():
        issues.append("missing:backend/api/market_public_routes.py")
    else:
        txt = market_py.read_text(encoding="utf-8", errors="replace")
        for s in ("BYBIT_MAINNET", "no-store", "api_key_used", "linear"):
            if s not in txt:
                issues.append(f"market_proxy_missing:{s}")

    print("NEXUS UI MVP-22A Live Market Data Truth Layer safety check")
    if issues:
        print(f"FAIL: {len(issues)} issue(s)")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("PASS: market truth layer files + Mainnet public markers present; no private/trade routes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
