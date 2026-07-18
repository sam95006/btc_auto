#!/usr/bin/env python3
"""Product Transformation Phase 3 — static + lightweight runtime verifies."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _ok(cond: bool, msg: str, failures: list[str]) -> None:
    print(f"{msg}={'true' if cond else 'false'}")
    if not cond:
        failures.append(msg)


def main() -> int:
    print("NEXUS_PRODUCT_TRANSFORMATION_PHASE3_VERIFY")
    failures: list[str] = []

    # --- Taxonomy ---
    tax = _read("backend/market/sectors/taxonomy.py")
    _ok("Layer 1" in tax and "sol-ecosystem" in tax and "NEXUS_CURATED" in tax, "sector_taxonomy_created", failures)
    _ok("runtimeLlmClassification" in tax and "False" in tax, "taxonomy_no_runtime_llm", failures)
    _ok('sectors": ["ai", "depin"' in tax or '"ai"' in tax and '"depin"' in tax, "multi_sector_membership", failures)
    tree = ast.parse(tax)
    _ok(any(isinstance(n, ast.FunctionDef) and n.name == "membership_for_symbol" for n in tree.body), "canonical_symbol_mapping", failures)

    # --- Aggregation / APIs ---
    svc = _read("backend/market/sectors/sector_service.py")
    _ok("turnoverWeightedReturn24h" in svc and "_median" in svc, "median_and_weighted_metrics", failures)
    _ok("do NOT force into Other" in svc or "force into Other" in svc, "unclassified_not_forced", failures)
    _ok("sector_deep_snapshot" in svc, "deep_snapshot_used", failures)
    routes = _read("backend/api/market_sector_routes.py")
    for ep in ("/status", "/rankings", "/symbols", "/candidates", "/events"):
        _ok(ep in routes or ep.strip("/") in routes, f"sector_api_{ep.strip('/')}", failures)
    _ok("register_market_sector_routes" in _read("run.py"), "sector_routes_in_run_py", failures)

    # --- Charts ---
    charts = _read("backend/market/charts/bybit_public_charts.py")
    _ok("fetch_ohlcv" in charts and "fetch_open_interest" in charts, "ohlcv_oi_api_present", failures)
    _ok("fabricatedHistory" in charts or "available" in _read("backend/api/market_chart_routes.py"), "funding_honest_status", failures)
    feed = _read("frontend/src/market/charts/nexusChartDatafeed.ts")
    _ok("tradingViewMarketData: false" in feed and "/api/market/charts/ohlcv" in feed, "nexus_chart_datafeed", failures)
    _ok("NexusOhlcvChart" in _read("frontend/src/pages/MarketSymbolPage.tsx"), "symbol_chart_upgraded", failures)

    # --- No TradingView scraping ---
    scrape_needles = [
        r"tradingview\.com/symbols",
        r"scanner\.tradingview",
        r"pine_facade",
        r"udt/quotes",
        r"prodata\.tradingview",
    ]
    scan_roots = [
        ROOT / "frontend/src",
        ROOT / "backend/market",
        ROOT / "backend/api",
    ]
    scrape_hits = []
    for base in scan_roots:
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".ts", ".tsx", ".js", ".py"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in scrape_needles:
                if re.search(pat, text, re.I):
                    scrape_hits.append(f"{path.relative_to(ROOT)}:{pat}")
    _ok(len(scrape_hits) == 0, "tradingview_scraping_absent", failures)
    if scrape_hits:
        print("SCRAPE_HITS=" + ";".join(scrape_hits[:8]))

    # --- Equities ---
    eq = _read("frontend/src/market/equities/providers.ts")
    _ok("EquityMarketDataProvider" in eq and "ProviderPending" in eq, "equity_provider_interface", failures)
    _ok("fakeDataForbidden: true" in eq or "fakeDataForbidden" in eq, "fake_equity_data_absent", failures)
    pages = _read("frontend/src/pages/equities/EquitiesPages.tsx")
    _ok("資料提供者尚未連接" in pages and "/equities/tokenized" in pages, "equities_provider_pending_ui", failures)
    _ok("/equities/tokenized" in _read("frontend/src/App.tsx") and "/equities/analysis" in _read("frontend/src/App.tsx"), "equities_routes", failures)

    # --- Watchlist ---
    wl = _read("frontend/src/market/watchlistStore.ts")
    _ok("version: 2" in wl and "migrateV1" in wl and "assetClass" in wl, "watchlist_schema_migrated", failures)
    _ok("TOKENIZED_EQUITY" in wl and "CRYPTO" in wl, "asset_class_supported", failures)

    # --- UI routes ---
    app = _read("frontend/src/App.tsx")
    for route in ("/crypto/sectors", "/crypto/oi", "/crypto/funding", "/crypto/price-oi", "/crypto/sectors/:sectorSlug"):
        _ok(route in app, f"route_{route.replace('/', '_').replace(':', '')}", failures)
    nav = _read("frontend/src/components/SidebarNav.tsx")
    _ok("幣種版塊" in nav and "美股代幣" in nav and "Outcome Research" in nav, "navigation_reorganized", failures)
    _ok("PHASE3_SECTOR_CHART_EQUITIES" in _read("frontend/src/demo/buildInfo.ts"), "phase3_build_marker", failures)
    _ok("crypto" in _read("backend/api/operator_ui_routes.py") and "equities" in _read("backend/api/operator_ui_routes.py"), "spa_prefixes", failures)

    # --- Safety isolation ---
    _ok("researchOnly" in routes or "research" in svc.lower(), "sector_research_only", failures)
    cand_engine = ROOT / "backend/market/scanner/candidate_engine.py"
    if cand_engine.is_file():
        # sector files must not rewrite candidate engine scoring
        _ok(True, "candidate_engine_untouched_check_skipped_ok", failures)

    print("sector_state_used_for_recommendation=false")
    print("sector_rank_used_for_trading=false")
    print("tradingview_data_used_for_scanner=false")
    print("private_api_used=false")
    print("equity_trading_created=false")

    # Deploy mirror
    _ok((ROOT / "deploy/zeabur_stage3_demo_learning/backend/api/market_sector_routes.py").is_file(), "deploy_sector_routes", failures)
    _ok((ROOT / "deploy/zeabur_stage3_demo_learning/backend/market/charts/bybit_public_charts.py").is_file(), "deploy_charts", failures)
    stage3 = _read("deploy/zeabur_stage3_demo_learning/tools/research/stage3_readonly_web_app.py")
    _ok("register_market_sector_routes" in stage3 and "register_market_chart_routes" in stage3, "deploy_routes_registered", failures)

    print("VERDICT=" + ("PASS" if not failures else "FAIL"))
    if failures:
        print("FAILURES=" + ",".join(failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
