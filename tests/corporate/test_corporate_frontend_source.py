"""Source-level assertions for the CORPORATE-1 frontend surface."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

FE = Path("frontend")
CORP = FE / "src" / "corporate"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _imports_founder(src: str) -> bool:
    for line in src.splitlines():
        s = line.strip()
        if not (s.startswith("import") or s.startswith("export")):
            continue
        if re.search(r'["\'][^"\']*founder[^"\']*["\']', s, re.IGNORECASE):
            return True
    return False


def test_corporate_app_routes_owner_and_admin() -> None:
    src = _read(FE / "src" / "surfaces" / "CorporateApp.tsx")
    assert "/owner/setup" in src and "/admin/login" in src and "/admin/*" in src


def test_corporate_is_backend_driven() -> None:
    client = _read(CORP / "api" / "client.ts")
    for fn in ("getSite", "getHome", "getMarket", "ownerSetup", "adminLogin", "adminSaveContent", "adminPublish"):
        assert fn in client, fn
    # Market showcase renders backend availability/provenance, never fabricates.
    live = _read(CORP / "components" / "LiveMarket.tsx")
    assert "unavailable" in live.lower() and "Provenance" in live


def test_corporate_no_founder_or_trading_imports() -> None:
    blob = ""
    for p in CORP.rglob("*.ts*"):
        src = _read(p)
        assert _imports_founder(src) is False, str(p)
        blob += src.lower()
    for banned in ("bybit", "orderexecutor", "durableorderledger", "exchange_write", "founderoperator",
                   "groq_api", "bybit_demo_api"):
        assert banned not in blob, banned


def test_corporate_no_fake_data_checker_passes() -> None:
    proc = subprocess.run(["node", "scripts/check_corporate_no_fake_data.mjs"], cwd=str(FE),
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CORPORATE_NO_FAKE_DATA_PASS" in proc.stdout


def test_corporate_states_and_reduced_motion() -> None:
    hook = _read(CORP / "hooks" / "useCorporate.ts")
    assert "prefers-reduced-motion" in hook and "IntersectionObserver" in hook
    ds = _read(CORP / "components" / "DataState.tsx")
    for state in ("LOADING", "UNAVAILABLE", "ERROR"):
        assert state in ds
    css = _read(FE / "src" / "styles" / "corporate.css")
    assert "prefers-reduced-motion" in css


# ---- CORPORATE-2 cinematic layer ----

def test_hero_is_backend_driven_with_fallback() -> None:
    hero = _read(CORP / "components" / "hero" / "FlagshipHero.tsx")
    # Split hero: motion from backend regime/energy; a real live console (product).
    assert "regime" in hero and "energy" in hero and "LiveConsole" in hero
    # R3F is lazy + only on desktop/non-reduced-motion, with a static fallback.
    assert "lazy(" in hero and "HeroFallback" in hero and "useHeavyOk" in hero
    assert (CORP / "components" / "hero" / "HeroFallback.tsx").exists()
    assert (CORP / "components" / "hero" / "IntelligenceR3F.tsx").exists()


# ---- CORPORATE-3 product-first ----

def test_product_console_and_command_center_backend_only() -> None:
    console = _read(CORP / "components" / "product" / "LiveConsole.tsx")
    assert "useMarket" in console and "暫不可用" in console  # explicit unavailable state
    cc = _read(CORP / "components" / "product" / "CommandCenter.tsx")
    assert "useMarket" in cc and "Sparkline" in cc
    # CORPORATE-4: homepage is SIMPLIFIED to six sections (hero, jobs, live product,
    # choice, trust, cta); the former modules are MERGED inside LiveProduct.
    home = _read(CORP / "pages" / "Home.tsx")
    for comp in ("FlagshipHero", "JobsSection", "LiveProduct", "ProductChoice", "TrustCompact", "ClosingCta"):
        assert comp in home, comp
    lp = _read(CORP / "components" / "product" / "LiveProduct.tsx")
    for merged in ("CommandCenter", "AttentionPanel", "IntelligenceFeed", "MarketBrief"):
        assert merged in lp, merged


def test_new_public_endpoints_in_client() -> None:
    client = _read(CORP / "api" / "client.ts")
    for fn in ("getHistory", "getEvents", "getBrief"):
        assert fn in client, fn


def test_market_brief_is_deterministic_not_ai() -> None:
    intel = _read(Path("backend") / "nexus_corporate" / "intelligence.py")
    assert "deterministic_rule_based" in intel
    brief = _read(CORP / "components" / "product" / "MarketBrief.tsx")
    assert "Deterministic" in brief  # labelled deterministic in the UI
    # the "not AI-generated" note is localized in the corporate i18n dict
    i18n = _read(CORP / "i18n" / "index.tsx")
    assert "非 AI 生成" in i18n and "not AI" in i18n


# ---- CORPORATE-4: simplify + theme + i18n + realtime ----

def test_theme_system_light_dark() -> None:
    ctx = _read(CORP / "context" / "ThemeContext.tsx")
    assert "system" in ctx and "light" in ctx and "dark" in ctx and "data-theme" in ctx
    css = _read(FE / "src" / "styles" / "corporate-theme.css")
    assert '[data-theme="dark"]' in css and "prefers-color-scheme: dark" in css
    assert "--ct-bg" in css and "--ct-accent" in css and "--ct-positive" in css  # semantic tokens
    html = _read(FE / "corporate.html")
    assert "nexus.corp.theme" in html  # no-flash inline script


def test_i18n_four_locales_no_bilingual_clutter() -> None:
    i18n = _read(CORP / "i18n" / "index.tsx")
    for loc in ("zh-TW", "en-US", "ja-JP", "ko-KR"):
        assert loc in i18n, loc
    # header nav uses localized keys, not baked "X / Y" bilingual strings
    chrome = _read(CORP / "components" / "Chrome.tsx")
    assert "useLocale" in chrome and "nav_products" in chrome
    assert " / Products" not in chrome and " / Personal" not in chrome


def test_realtime_sse_with_fallback_and_no_binance() -> None:
    ctx = _read(CORP / "context" / "MarketContext.tsx")
    assert "EventSource" in ctx and "market_snapshot" in ctx
    assert "reconnect" in ctx.lower() and "poll" in ctx.lower()  # fallback + reconnect
    # never a direct Binance URL/endpoint (data flows only via the backend)
    assert "binance.com" not in ctx.lower() and "fapi.binance" not in ctx.lower()
    routes = _read(Path("backend") / "nexus_corporate" / "routes.py")
    assert "text/event-stream" in routes and "/api/corporate/v1/stream" in routes


def test_content_and_brief_are_locale_aware() -> None:
    routes = _read(Path("backend") / "nexus_corporate" / "routes.py")
    assert "normalize_locale" in routes and "@{locale}" in routes  # slug@locale lookup
    client = _read(CORP / "api" / "client.ts")
    assert "getLocales" in client and "withLocale" in client


def test_sparkline_uses_backend_history_only() -> None:
    sp = _read(CORP / "components" / "product" / "Sparkline.tsx")
    assert "getHistory" in sp and "points" in sp
    # renders nothing until real points arrive (no fabricated series)
    assert "length < 2" in sp


def test_live_showcase_has_explicit_states() -> None:
    sc = _read(CORP / "components" / "LiveShowcase.tsx")
    for token in ("LOADING", "ERROR", "UNAVAILABLE", "provenance", "freshness"):
        assert token.lower() in sc.lower(), token
    # no fabricated interpolation — flashes on real value change only
    assert "tick-up" in sc and "prev" in sc


def test_scroll_engine_and_cinematic_css_respect_reduced_motion() -> None:
    scroll = _read(CORP / "hooks" / "useScrollScene.ts")
    assert "prefers-reduced-motion" in scroll
    css = _read(FE / "src" / "styles" / "corporate-cinematic.css")
    assert "prefers-reduced-motion" in css and "corp-skip-link" in css


def test_market_context_polls_backend_only() -> None:
    ctx = _read(CORP / "context" / "MarketContext.tsx")
    assert "getMarket" in ctx and "UNAVAILABLE" in ctx and "ERROR" in ctx
    # energy is derived from the backend regime/risk (motion only), not invented
    assert "energyOf" in ctx and "regimeOf" in ctx


def test_static_server_sets_csp_and_security_headers() -> None:
    srv = _read(Path("deploy") / "zeabur_corporate_v1" / "server.py")
    for token in ("Content-Security-Policy", "frame-ancestors 'none'", "X-Content-Type-Options",
                  "Referrer-Policy", "Permissions-Policy", "/robots.txt", "/sitemap.xml"):
        assert token in srv, token
    # CSP must not permit inline scripts.
    assert "script-src 'self'" in srv and "'unsafe-inline'" not in srv.split("script-src", 1)[1].split(";", 1)[0]
