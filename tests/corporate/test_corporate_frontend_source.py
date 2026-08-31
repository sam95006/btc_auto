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
    hero = _read(CORP / "components" / "hero" / "IntelligenceHero.tsx")
    # Motion/colour come from backend regime/energy props — not decided here.
    assert "regime" in hero and "energy" in hero and "available" in hero
    # A static fallback exists for reduced-motion / no-canvas / Suspense.
    assert (CORP / "components" / "hero" / "HeroFallback.tsx").exists()
    home = _read(CORP / "pages" / "Home.tsx")
    assert "reducedMotion" in home and "HeroFallback" in home and "lazy(" in home


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
