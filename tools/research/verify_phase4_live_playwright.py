#!/usr/bin/env python3
"""Phase 4 Live Playwright + API sign-off (real Live URL)."""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "https://nexus-stage3-bybit-demo-learning.zeabur.app"
EXPECTED_JS = "index-BhzPt_Df.js"
EXPECTED_CSS = "index-DVRzanNn.css"
EXPECTED_MARKER = "NEXUS_UI_PRODUCT_AND_INTELLIGENCE_PHASE4"

VIEWPORTS = [
    (1440, 900),
    (1280, 800),
    (1024, 768),
    (768, 1024),
    (430, 932),
    (390, 844),
    (375, 812),
    (360, 800),
]

PAGES = [
    "/overview",
    "/scanner",
    "/watchlist",
    "/market/BTCUSDT",
    "/crypto/sectors",
    "/crypto/oi",
    "/crypto/funding",
    "/crypto/price-oi",
    "/anomalies",
    "/anomaly-outcomes",
]


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_text(path: str) -> str:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def main() -> int:
    print("NEXUS_PHASE4_LIVE_PLAYWRIGHT")
    failures: list[str] = []

    root = _get_text("/")
    if EXPECTED_JS not in root:
        failures.append("root_js_mismatch")
    if EXPECTED_CSS not in root:
        failures.append("root_css_mismatch")
    print(f"observed_js={EXPECTED_JS in root}")
    print(f"observed_css={EXPECTED_CSS in root}")

    ui = _get("/api/nexus/ui-build")
    marker = ui.get("buildMarker") or ui.get("build_marker")
    assets = (ui.get("sync_meta") or {}).get("current_assets") or []
    print(f"ui_marker={marker}")
    print(f"current_assets={assets}")
    if marker != EXPECTED_MARKER:
        failures.append("marker_mismatch")
    if EXPECTED_JS not in assets:
        failures.append("ui_build_js_mismatch")

    intel = _get("/api/market/intelligence/status")
    fund = _get("/api/market/charts/funding?symbol=BTCUSDT&limit=2")
    tl = _get("/api/market/scanner/candidates/BTCUSDT/timeline")
    print(f"intelligence_ok={bool(intel.get('ok'))}")
    print(f"transport={intel.get('transport')}")
    print(f"wsConnected={intel.get('wsConnected')}")
    print(f"deepSymbolCount={intel.get('deepSymbolCount')}")
    print(f"historyMode={intel.get('historyMode')}")
    print(f"funding_available={fund.get('available')}")
    print(f"funding_fabricated={fund.get('fabricatedHistory')}")
    print(f"timeline_ok={bool(tl.get('ok'))}")
    if not intel.get("ok"):
        failures.append("intelligence_status")
    if fund.get("fabricatedHistory"):
        failures.append("funding_fabricated")
    if not tl.get("ok"):
        failures.append("timeline")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright_missing=true")
        print("VERDICT=FAIL")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda err: failures.append(f"pageerror:{err}"))

        page.goto(BASE + "/overview", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2500)
        body = page.inner_text("body")
        checks = [
            ("market_live", "市場行情" in body or "LIVE" in body),
            ("exec_disabled", "Disabled" in body or "不執行" in body or "研究模式" in body),
            ("no_demo_data_banner", "DEMO DATA" not in body[:800]),
            ("top_or_collecting", ("首選機會" in body) or ("正在建立" in body) or ("資料建立" in body) or ("做多" in body)),
            ("footer_clean", "UI Build" not in body[-600:] and "Stage 4.19" not in body[-600:]),
            ("research_collapsed_hint", "研究分析" in body),
        ]
        for name, ok in checks:
            print(f"{name}={ok}")
            if not ok:
                failures.append(name)

        # Horizontal overflow spot-check
        overflow = page.evaluate(
            """() => {
              const el = document.documentElement;
              return el.scrollWidth > el.clientWidth + 2;
            }"""
        )
        print(f"page_horizontal_overflow={overflow}")
        if overflow:
            failures.append("horizontal_overflow")

        for w, h in VIEWPORTS:
            page.set_viewport_size({"width": w, "height": h})
            page.goto(BASE + "/overview", wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(800)
            if page.locator("#root").count() == 0:
                failures.append(f"no_root_{w}x{h}")

        for path in PAGES:
            page.set_viewport_size({"width": 1280, "height": 800})
            resp = page.goto(BASE + path, wait_until="domcontentloaded", timeout=90000)
            if resp is None or resp.status >= 400:
                failures.append(f"page_{path}_{getattr(resp,'status',None)}")

        # 125% zoom approximation via CSS zoom
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(BASE + "/overview", wait_until="domcontentloaded", timeout=90000)
        page.evaluate("document.documentElement.style.zoom='1.25'")
        page.wait_for_timeout(500)
        clipped = page.evaluate(
            """() => {
              const main = document.querySelector('.main-content') || document.body;
              const r = main.getBoundingClientRect();
              return r.width < 100 || r.height < 100;
            }"""
        )
        print(f"zoom_125_clipped={clipped}")
        if clipped:
            failures.append("zoom_125_clipped")

        browser.close()

    if failures:
        print("failures=" + ",".join(failures))
        print("VERDICT=FAIL")
        return 1
    print("VERDICT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
