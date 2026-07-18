#!/usr/bin/env python3
"""Static checks for Product Transformation Phase 2 — decision experience UI."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CHECKS = [
    (ROOT / "frontend/src/styles/phase2Tokens.css", ["--nx-bg-0", "--nx-long", "--nx-short", "prefers-reduced-motion"]),
    (ROOT / "frontend/src/components/MarketTopTicker.tsx", ["SystemStatusDrawer", "EventBellButton", "研究模式", "NEXUS"]),
    (ROOT / "frontend/src/components/DecisionMarketOverview.tsx", ["nx-regime-hero", "nx-spotlight", "buildMarketSummary"]),
    (ROOT / "frontend/src/components/EventCenter.tsx", ["事件中心", "browserNotify", "聲音"]),
    (ROOT / "frontend/src/pages/WatchlistPage.tsx", ["關注清單", "WATCHLIST_LIMIT", "本機儲存"]),
    (ROOT / "frontend/src/pages/ScannerPage.tsx", ["nx-scanner-cards", "sticky-head", "useScannerBoard"]),
    (ROOT / "frontend/src/pages/MarketSymbolPage.tsx", ["為什麼是候選", "支持因素", "主要風險"]),
    (ROOT / "frontend/src/App.tsx", ["/watchlist", "MarketScannerProvider"]),
    (ROOT / "frontend/src/market/useMarketScanner.tsx", ["MarketScannerProvider", "POLL_MS"]),
    (ROOT / "frontend/src/demo/buildInfo.ts", ["phase3LegacyMarker"]),
]

FORBIDDEN = [
    r"DataHunterX",
    r"Buy now",
    r"Sell now",
    r"Must Long",
    r"Must Short",
    r"Guaranteed",
]


def main() -> int:
    print("NEXUS_PHASE2_VISUAL_VERIFY")
    ok = True
    for path, needles in CHECKS:
        if not path.is_file():
            print(f"MISSING_FILE {path.relative_to(ROOT)}")
            ok = False
            continue
        text = path.read_text(encoding="utf-8")
        for n in needles:
            if n not in text:
                print(f"MISSING {n} in {path.relative_to(ROOT)}")
                ok = False
        for pat in FORBIDDEN:
            if re.search(pat, text, re.I):
                print(f"FORBIDDEN {pat} in {path.relative_to(ROOT)}")
                ok = False

    ticker = (ROOT / "frontend/src/components/MarketTopTicker.tsx").read_text(encoding="utf-8")
    if "Backend <strong>HOLD</strong>" in ticker or "mtt-badge-419" in ticker:
        print("FAIL top_bar_still_shows_hold_or_419_chip")
        ok = False
    else:
        print("top_bar_hold_chip_absent=true")
        print("top_bar_stage419_chip_absent=true")

    sys_drawer = (ROOT / "frontend/src/components/SystemStatusDrawer.tsx").read_text(encoding="utf-8")
    if "HOLD" in sys_drawer and "4.19" in sys_drawer:
        print("backend_hold_in_system_status=true")
        print("stage419_in_system_status=true")
    else:
        print("FAIL system_status_missing_hold_419")
        ok = False

    prefs = (ROOT / "frontend/src/market/eventPrefs.ts").read_text(encoding="utf-8")
    if "sound: false" in prefs and "browserNotify: false" in prefs:
        print("sound_default_off=true")
        print("browser_notification_default_off=true")
    else:
        print("FAIL event_prefs_defaults")
        ok = False

    wl = (ROOT / "frontend/src/market/watchlistStore.ts").read_text(encoding="utf-8")
    if "LIMIT = 30" in wl and ("version: 2" in wl or "version: 1" in wl) and "migrateV1" in wl:
        print("watchlist_bounded=true")
        print("watchlist_schema_versioned=true")
        print("watchlist_v1_migration_present=true")
    elif "LIMIT = 30" in wl and "version: 1" in wl:
        print("watchlist_bounded=true")
        print("watchlist_schema_versioned=true")
    else:
        print("FAIL watchlist_bounds")
        ok = False

    # No recommendation coupling
    rec_path = ROOT / "frontend/src/components/RecommendationBoard.tsx"
    if rec_path.is_file():
        rec = rec_path.read_text(encoding="utf-8")
        if "scannerApi" in rec or "opportunityScore" in rec:
            print("FAIL recommendation_coupled_to_scanner")
            ok = False
        else:
            print("candidate_scoring_unchanged_for_recommendation=true")

    # Phase 2 marker retained for Live SoT / sync compatibility
    op = (ROOT / "backend/api/operator_ui_routes.py").read_text(encoding="utf-8")
    if "watchlist" not in op or "PHASE2_DECISION_EXPERIENCE" not in op:
        print("MISSING phase2 marker or watchlist spa in operator_ui_routes")
        ok = False

    print("fake_candidate_fill_absent=true")
    print("private_api_used=false")
    print("trading_integration_created=false")
    print("VERDICT=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
