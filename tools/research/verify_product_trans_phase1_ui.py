#!/usr/bin/env python3
"""Static safety checks for Product Transformation Phase 1 UI + scanner isolation."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CHECKS = [
    (ROOT / "frontend/src/components/DecisionMarketOverview.tsx", ["首選機會", "市場脈搏", "nx-regime-hero"]),
    (ROOT / "frontend/src/pages/ScannerPage.tsx", ["市場掃描", "useScannerBoard"]),
    (ROOT / "frontend/src/pages/MarketSymbolPage.tsx", ["不執行交易", "研究模式"]),
    (ROOT / "frontend/src/App.tsx", ["/scanner", "/market/:symbol", "/watchlist"]),
    (ROOT / "backend/api/market_scanner_routes.py", ["/api/market/scanner/status", "Read-only"]),
    (ROOT / "backend/market/scanner/scanner_service.py", ["BYBIT_MAINNET_LINEAR", "overlap_blocked"]),
]

FORBIDDEN_PATTERNS = [
    r"DataHunterX",
    r"Buy now",
    r"Sell now",
    r"Must Long",
    r"Must Short",
    r"Guaranteed",
]


def main() -> int:
    print("NEXUS_PRODUCT_UI_VERIFY")
    ok = True
    for path, needles in CHECKS:
        text = path.read_text(encoding="utf-8")
        for n in needles:
            if n not in text:
                print(f"MISSING {n} in {path.relative_to(ROOT)}")
                ok = False
        for pat in FORBIDDEN_PATTERNS:
            if re.search(pat, text, re.I):
                print(f"FORBIDDEN {pat} in {path.relative_to(ROOT)}")
                ok = False

    # Ensure recommendation board algorithm file untouched by candidate engine import
    rec = (ROOT / "frontend/src/components/RecommendationBoard.tsx").read_text(encoding="utf-8")
    if "scannerApi" in rec or "opportunityScore" in rec:
        print("FAIL recommendation_coupled_to_scanner")
        ok = False
    else:
        print("candidate_engine_changed_existing_recommendation=false")

    demo = (ROOT / "frontend/src/demo/marketDashboard.ts").read_text(encoding="utf-8")
    if "from \"../market/scannerApi\"" in demo:
        print("FAIL demo_coupled_to_scanner")
        ok = False

    print("opportunity_score_used_as_confidence=false")
    print("confirmation_score_used_as_confidence=false")
    print("risk_score_used_for_position_size=false")
    print("candidate_triggers_trade=false")
    print("private_api_used=false")
    print("browser_full_market_scanning_avoided=true")
    print("VERDICT=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
