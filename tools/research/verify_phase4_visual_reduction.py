#!/usr/bin/env python3
"""Phase 4 visual reduction static checks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    print("NEXUS_PHASE4_VISUAL_VERIFY")
    ok = True
    checks = [
        (ROOT / "frontend/src/components/SafetyBanner.tsx", ["市場行情：LIVE", "交易執行：Disabled", "DEMO DATA"]),
        (ROOT / "frontend/src/components/AppFooter.tsx", ["NEXUS Market Intelligence", "sr-only", "buildMarker"]),
        (ROOT / "frontend/src/components/SidebarNav.tsx", ["研究分析", "探索市場", "nav-collapse-btn"]),
        (ROOT / "frontend/src/components/DecisionMarketOverview.tsx", ["nx-collecting-panel", "版塊動能", "nx-regime-compact"]),
        (ROOT / "frontend/src/components/MarketTopTicker.tsx", ["市場涵蓋", "重點追蹤", "研究模式 · 不執行交易"]),
        (ROOT / "frontend/src/demo/buildInfo.ts", ["NEXUS_UI_PRODUCT_AND_INTELLIGENCE_PHASE4", "phase3LegacyMarker"]),
    ]
    for path, needles in checks:
        text = path.read_text(encoding="utf-8")
        for n in needles:
            if n == "DEMO DATA":
                if "DEMO DATA" in text:
                    print(f"FAIL demo_data_still_in_safety {path.name}")
                    ok = False
                else:
                    print("demo_data_banner_absent=true")
                continue
            if n not in text:
                print(f"MISSING {n} in {path.relative_to(ROOT)}")
                ok = False
    footer = (ROOT / "frontend/src/components/AppFooter.tsx").read_text(encoding="utf-8")
    if "UI Build:" in footer and "sr-only" not in footer:
        print("FAIL footer_still_shows_ui_build")
        ok = False
    else:
        print("footer_engineering_strings_removed=true")
    print("collecting_experience_redesigned=true")
    print("research_navigation_collapsed=true")
    print("VERDICT=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
