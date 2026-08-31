from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _imports_founder(src: str) -> bool:
    # A real import/export of the founder tree — a module specifier (quoted path)
    # whose path contains "founder". Doc comments that merely mention Founder do
    # not count.
    for line in src.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("import") or stripped.startswith("export")):
            continue
        if re.search(r'["\'][^"\']*founder[^"\']*["\']', stripped, re.IGNORECASE):
            return True
    return False

FE = Path("frontend")
SRC = FE / "src"
APP = SRC / "App.tsx"
MAIN = SRC / "main.tsx"
VITE = FE / "vite.config.ts"
PKG = FE / "package.json"
CORP = SRC / "surfaces" / "CorporateApp.tsx"
ENT = SRC / "surfaces" / "EnterpriseApp.tsx"
FOUND = SRC / "surfaces" / "FounderApp.tsx"
CORP_MAIN = SRC / "entries" / "corporateMain.tsx"
ENT_MAIN = SRC / "entries" / "enterpriseMain.tsx"
FOUND_MAIN = SRC / "entries" / "founderMain.tsx"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Build architecture
# --------------------------------------------------------------------------

def test_vite_config_defines_four_surfaces() -> None:
    src = _read(VITE)
    for surface in ("personal", "corporate", "enterprise", "founder"):
        assert f"{surface}:" in src
    assert "NEXUS_SURFACE" in src
    assert "index.html" in src and "corporate.html" in src and "enterprise.html" in src and "founder.html" in src


def test_build_scripts_present() -> None:
    src = _read(PKG)
    for script in ("build:personal", "build:corporate", "build:enterprise", "build:founder", "build:all", "check:surface-boundary"):
        assert f'"{script}"' in src


def test_surface_html_entrypoints_exist_and_reference_correct_mains() -> None:
    assert "/src/main.tsx" in _read(FE / "index.html")
    assert "/src/entries/corporateMain.tsx" in _read(FE / "corporate.html")
    assert "/src/entries/enterpriseMain.tsx" in _read(FE / "enterprise.html")
    assert "/src/entries/founderMain.tsx" in _read(FE / "founder.html")


# --------------------------------------------------------------------------
# Public/private boundary (source level)
# --------------------------------------------------------------------------

def test_personal_app_does_not_import_founder() -> None:
    assert _imports_founder(_read(APP)) is False


def test_personal_main_does_not_load_founder_css() -> None:
    src = _read(MAIN)
    # founderOperator.css must not be loaded by the personal entry.
    assert 'import "./styles/founderOperator.css"' not in src


def test_founder_surface_only_in_founder_entry() -> None:
    # FounderApp imports the founder tree; corporate/enterprise entries do not.
    fsrc = _read(FOUND)
    assert "../founder/FounderOperatorPage" in fsrc
    assert "FounderRuntimePage" in fsrc
    assert "FounderApp" in _read(FOUND_MAIN)
    for entry in (CORP_MAIN, ENT_MAIN):
        assert _imports_founder(_read(entry)) is False


def test_corporate_and_enterprise_do_not_import_founder_or_personal_billing() -> None:
    for surface in (CORP, ENT):
        src = _read(surface)
        assert _imports_founder(src) is False
        # Enterprise/Corporate must not reuse the personal authenticated Billing center.
        assert "BillingCenterPage" not in src
        assert "BillingPages" not in src
        # No AI-agent product, no private trading controls.
        for banned in ("AgentPlatform", "agent-workflow", "/routing-edit", "arm-control", "OrderExecutor"):
            assert banned not in src


def test_corporate_has_personal_and_enterprise_product_entries() -> None:
    # CORPORATE-1: the corporate site routes to Personal + Enterprise product
    # pages, and the site chrome links out to the separate apps (login-personal /
    # login-enterprise data-testids live in the Chrome component).
    src = _read(CORP)
    assert '/personal' in src and '/enterprise' in src
    chrome = _read(SRC / "corporate" / "components" / "Chrome.tsx")
    assert 'login-personal' in chrome and 'login-enterprise' in chrome


def test_enterprise_is_independent_shell_not_personal_subroute() -> None:
    src = _read(ENT)
    assert "Enterprise" in src
    assert "enterprise-authenticated-placeholder" in src


# --------------------------------------------------------------------------
# Boundary check script actually passes (runnable)
# --------------------------------------------------------------------------

def test_surface_boundary_check_script_passes() -> None:
    proc = subprocess.run(
        ["node", "scripts/check_surface_boundary.mjs"],
        cwd=str(FE),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SURFACE_BOUNDARY_PASS" in proc.stdout
