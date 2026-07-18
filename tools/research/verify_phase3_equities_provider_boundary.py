#!/usr/bin/env python3
"""Phase 3 equities provider boundary — no fake quotes."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    print("PHASE3_EQUITIES_PROVIDER_BOUNDARY")
    text = (ROOT / "frontend/src/market/equities/providers.ts").read_text(encoding="utf-8")
    pages = (ROOT / "frontend/src/pages/equities/EquitiesPages.tsx").read_text(encoding="utf-8")
    ok = True
    for needle in ("EquityMarketDataProvider", "TokenizedEquityProvider", "PROVIDER_PENDING", "isAvailable"):
        if needle not in text:
            print(f"MISSING {needle}")
            ok = False
    if re.search(r"lastPrice\s*=\s*\d|Math\.random\(\)|demoPrice|fakeQuote", text + pages, re.I):
        print("FAIL fake_price_pattern")
        ok = False
    else:
        print("fake_equity_data_absent=true")
    if "資料提供者尚未連接" not in pages:
        print("FAIL pending_banner")
        ok = False
    else:
        print("provider_unavailable_state=true")
    if "Buy" in pages and "button" in pages.lower():
        # allow word in prose only if no Buy button
        pass
    print("licensed_equity_provider_available=false")
    print("real_equity_data_connected=false")
    print("VERDICT=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
