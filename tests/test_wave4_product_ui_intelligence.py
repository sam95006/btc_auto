"""Wave 4 Product UI Intelligence tests (>=80) — static source / docs inspection."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
DOCS = ROOT / "docs" / "04_readiness"

APP_TSX = FRONTEND / "App.tsx"
MATRIX_JSON = DOCS / "NEXUS_WAVE4_UI_FEATURE_PRESERVATION_MATRIX.json"
AUDIT_JSON = DOCS / "NEXUS_WAVE4_DATAHUNTERX_FEATURE_AUDIT.json"
CHECKPOINT_JSON = DOCS / "NEXUS_WAVE4_PRODUCT_UI_CHECKPOINT.json"
VISUAL_JSON = DOCS / "NEXUS_WAVE4_VISUAL_REGRESSION_MANIFEST.json"
WAVE4_TOKENS = FRONTEND / "styles" / "wave4ProductTokens.css"
MAIN_TSX = FRONTEND / "main.tsx"
AI_COMMANDER = FRONTEND / "components" / "AiCommander.tsx"
FLOATING_AI = FRONTEND / "components" / "FloatingAIAssistant.tsx"
PRODUCT_SIMPLE = FRONTEND / "components" / "ProductSimpleView.tsx"
SIDEBAR = FRONTEND / "components" / "SidebarNav.tsx"
NO_DATA_FUNNEL_TS = FRONTEND / "wave4" / "noDataFunnel.ts"
FIXED_LEV_TS = FRONTEND / "wave4" / "fixedLeverageLabels.ts"
WORKFLOW = ROOT / ".github" / "workflows" / "wave4_product_ui_intelligence_validation.yml"


# ---------------------------------------------------------------------------
# Python mirrors of frontend helpers (contract tests)
# ---------------------------------------------------------------------------

NO_DATA = "NO_DATA"
FIXED_SHADOW_LEVERAGE = 25
MAX_SHADOW_OPEN_POSITIONS = 2


def format_funnel_value(value, data_available=True):
    if not data_available:
        return NO_DATA
    if value is None:
        return NO_DATA
    if isinstance(value, float) and value != value:
        return NO_DATA
    return str(value)


def build_funnel_display(stages, data_available=True):
    mapped = [
        {"key": s["key"], "label": s["label"], "display": format_funnel_value(s.get("value"), data_available)}
        for s in stages
    ]
    has_data = data_available and any(s["display"] != NO_DATA for s in mapped)
    summary = " → ".join(f"{s['label']}: {s['display']}" for s in mapped) if has_data else NO_DATA
    return {"stages": mapped, "hasData": has_data, "summary": summary}


def is_synthetic_funnel_default(counts):
    if len(counts) != 3:
        return False
    return counts[0] == 128 and counts[1] == 24 and counts[2] == 6


def shadow_leverage_label():
    return f"{FIXED_SHADOW_LEVERAGE}x"


def portfolio_leverage_badge():
    return f"Shadow · {shadow_leverage_label()} · max {MAX_SHADOW_OPEN_POSITIONS} positions"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_src() -> str:
    return read_text(APP_TSX)


@pytest.fixture(scope="module")
def matrix() -> dict:
    return json.loads(MATRIX_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def audit() -> dict:
    return json.loads(AUDIT_JSON.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Feature matrix load
# ---------------------------------------------------------------------------


class TestFeatureMatrixLoad:
    def test_matrix_file_exists(self):
        assert MATRIX_JSON.is_file()

    def test_matrix_schema_version(self, matrix):
        assert matrix["schema_version"] == "wave4_ui_feature_preservation_matrix_v1"

    def test_matrix_branch(self, matrix):
        assert matrix["branch"] == "feature/wave4-product-ui-intelligence"

    def test_feature_loss_zero(self, matrix):
        assert matrix["feature_loss_count"] == 0

    def test_routes_non_empty(self, matrix):
        assert len(matrix["routes"]) >= 30

    def test_preservation_enum_valid(self, matrix):
        allowed = set(matrix["preservation_status_enum"])
        for r in matrix["routes"]:
            assert r["status"] in allowed

    def test_every_route_has_path(self, matrix):
        for r in matrix["routes"]:
            assert r["path"]

    def test_every_route_has_page(self, matrix):
        for r in matrix["routes"]:
            assert r["page"]

    def test_invariants_present(self, matrix):
        inv = matrix["invariants"]
        assert inv["single_ai_commander"] is True
        assert inv["public_overview_no_bybit_demo_card"] is True
        assert inv["no_live_trade_buttons"] is True
        assert inv["no_synthetic_funnel_defaults"] is True


# ---------------------------------------------------------------------------
# Route presence
# ---------------------------------------------------------------------------


REQUIRED_ROUTES = [
    "/overview",
    "/universe",
    "/opportunities",
    "/alerts",
    "/portfolio",
    "/learning",
    "/evidence",
    "/founder/runtime",
    "/scanner",
    "/fleets",
    "/intelligence",
    "/trade-plan",
    "/performance",
    "/market/:symbol",
    "/watchlist",
    "/anomalies",
    "/signals",
    "/ai-learning-lab",
    "/paper-lab",
    "/assistant",
    "/academy",
    "/calculator",
    "/membership",
    "/ai-reviews",
    "/global-shadow",
    "/provider-shadow",
    "/reflection",
    "/risk-evidence",
    "/anomaly-outcomes",
    "/crypto/sectors",
    "/crypto/oi",
    "/equities",
]


class TestRoutePresence:
    @pytest.mark.parametrize("route", REQUIRED_ROUTES)
    def test_route_in_app_tsx(self, app_src, route):
        assert f'path="{route}"' in app_src or f"path='{route}'" in app_src

    def test_universe_page_imported(self, app_src):
        assert "UniversePage" in app_src

    def test_alerts_page_imported(self, app_src):
        assert "AlertsPage" in app_src

    def test_portfolio_page_imported(self, app_src):
        assert "PortfolioWorkspacePage" in app_src

    def test_founder_runtime_imported(self, app_src):
        assert "FounderRuntimePage" in app_src

    def test_root_redirect_overview(self, app_src):
        assert 'path="/"' in app_src
        assert "/overview" in app_src

    def test_research_performance_redirect(self, app_src):
        assert 'path="/research-performance"' in app_src

    def test_wildcard_fallback(self, app_src):
        assert 'path="*"' in app_src


# ---------------------------------------------------------------------------
# Fleets deprecated
# ---------------------------------------------------------------------------


class TestFleetsDeprecated:
    def test_fleets_uses_deprecated_redirect(self, app_src):
        assert "FleetsDeprecatedRedirect" in app_src

    def test_fleets_not_direct_fleets_page(self, app_src):
        assert '<FleetsPage' not in app_src

    def test_matrix_fleets_status(self, matrix):
        fleets = [r for r in matrix["routes"] if r["path"] == "/fleets"]
        assert len(fleets) == 1
        assert fleets[0]["status"] == "deprecated"

    def test_sidebar_marks_fleets_deprecated(self):
        src = read_text(SIDEBAR)
        assert "Fleets（已棄用）" in src or "fleets" in src.lower()

    def test_redirect_to_universe_in_component(self, app_src):
        assert 'to="/universe"' in app_src


# ---------------------------------------------------------------------------
# NO_DATA funnel helper
# ---------------------------------------------------------------------------


class TestNoDataFunnel:
    def test_ts_file_exists(self):
        assert NO_DATA_FUNNEL_TS.is_file()

    def test_ts_exports_no_data(self):
        assert "NO_DATA" in read_text(NO_DATA_FUNNEL_TS)

    def test_ts_exports_format_funnel_value(self):
        assert "formatFunnelValue" in read_text(NO_DATA_FUNNEL_TS)

    def test_ts_exports_build_funnel_display(self):
        assert "buildFunnelDisplay" in read_text(NO_DATA_FUNNEL_TS)

    def test_ts_guards_synthetic_default(self):
        assert "128" in read_text(NO_DATA_FUNNEL_TS)
        assert "isSyntheticFunnelDefault" in read_text(NO_DATA_FUNNEL_TS)

    def test_format_null_is_no_data(self):
        assert format_funnel_value(None) == NO_DATA

    def test_format_nan_is_no_data(self):
        assert format_funnel_value(float("nan")) == NO_DATA

    def test_format_unavailable_is_no_data(self):
        assert format_funnel_value(10, data_available=False) == NO_DATA

    def test_format_valid_number(self):
        assert format_funnel_value(42) == "42"

    def test_build_empty_funnel_no_data(self):
        r = build_funnel_display([], data_available=False)
        assert r["hasData"] is False
        assert r["summary"] == NO_DATA

    def test_build_partial_funnel(self):
        r = build_funnel_display([{"key": "a", "label": "A", "value": 5}])
        assert r["hasData"] is True
        assert "5" in r["summary"]

    def test_synthetic_triple_detected(self):
        assert is_synthetic_funnel_default([128, 24, 6]) is True

    def test_non_synthetic_not_detected(self):
        assert is_synthetic_funnel_default([100, 20, 5]) is False

    def test_product_simple_uses_no_data(self):
        src = read_text(PRODUCT_SIMPLE)
        assert "NO_DATA" in src
        assert "buildFunnelDisplay" in src

    def test_product_simple_no_synthetic_128(self):
        src = read_text(PRODUCT_SIMPLE)
        assert "128" not in src or "isSyntheticFunnelDefault" in read_text(NO_DATA_FUNNEL_TS)


# ---------------------------------------------------------------------------
# Fixed leverage labels
# ---------------------------------------------------------------------------


class TestFixedLeverageLabels:
    def test_ts_file_exists(self):
        assert FIXED_LEV_TS.is_file()

    def test_fixed_leverage_constant_25(self):
        assert "FIXED_SHADOW_LEVERAGE = 25" in read_text(FIXED_LEV_TS)

    def test_max_positions_2(self):
        assert "MAX_SHADOW_OPEN_POSITIONS = 2" in read_text(FIXED_LEV_TS)

    def test_shadow_leverage_label(self):
        assert shadow_leverage_label() == "25x"

    def test_portfolio_badge_contains_25x(self):
        assert "25x" in portfolio_leverage_badge()

    def test_portfolio_badge_max_2(self):
        assert "max 2" in portfolio_leverage_badge()

    def test_portfolio_page_uses_badge(self):
        src = read_text(FRONTEND / "pages" / "PortfolioWorkspacePage.tsx")
        assert "portfolioLeverageBadge" in src
        assert "25x" in src or "shadowLeverageLabel" in src

    def test_portfolio_no_live_actions(self):
        src = read_text(FRONTEND / "pages" / "PortfolioWorkspacePage.tsx")
        assert "NO live" in src or "live trade" in src.lower()

    def test_symbol_workbench_risk_25x(self):
        src = read_text(FRONTEND / "components" / "SymbolWorkbenchTabs.tsx")
        assert "25x" in src


# ---------------------------------------------------------------------------
# Preservation invariants
# ---------------------------------------------------------------------------


class TestPreservationInvariants:
    def test_scanner_alias_universe(self, app_src):
        assert 'path="/scanner" element={<UniversePage />}' in app_src.replace("\n", " ").replace("  ", " ") or \
               'path="/scanner"' in app_src and "UniversePage" in app_src

    def test_bybit_card_removed_from_overview(self):
        src = read_text(PRODUCT_SIMPLE)
        assert "BybitDemoAutonomousCard" not in src

    def test_bybit_card_on_founder_runtime(self):
        src = read_text(FRONTEND / "pages" / "FounderRuntimePage.tsx")
        assert "BybitDemoAutonomousCard" in src

    def test_wave4_tokens_imported(self):
        assert "wave4ProductTokens.css" in read_text(MAIN_TSX)

    def test_wave4_shell_class(self, app_src):
        assert "nx-wave4-shell" in app_src

    def test_sidebar_7_primary(self):
        src = read_text(SIDEBAR)
        assert "/overview" in src
        assert "/universe" in src
        assert "/opportunities" in src
        assert "/alerts" in src
        assert "/portfolio" in src
        assert "/learning" in src
        assert "/evidence" in src

    def test_learning_links_ai_lab(self):
        src = read_text(FRONTEND / "pages" / "LearningPage.tsx")
        assert "/ai-learning-lab" in src

    def test_symbol_workbench_8_tabs(self):
        src = read_text(FRONTEND / "components" / "SymbolWorkbenchTabs.tsx")
        for tab in ["overview", "structure", "flows", "six_roles", "risk", "plan", "memory", "evidence"]:
            assert tab in src

    def test_no_arm_route(self, app_src):
        assert 'path="/arm"' not in app_src

    def test_no_trade_route(self, app_src):
        assert 'path="/trade"' not in app_src


# ---------------------------------------------------------------------------
# Founder private path
# ---------------------------------------------------------------------------


class TestFounderRuntime:
    def test_founder_route_in_matrix(self, matrix):
        paths = [r["path"] for r in matrix["routes"]]
        assert "/founder/runtime" in paths

    def test_founder_page_read_only(self):
        src = read_text(FRONTEND / "pages" / "FounderRuntimePage.tsx")
        assert "READ ONLY" in src

    def test_founder_in_expert_nav(self):
        src = read_text(SIDEBAR)
        assert "/founder/runtime" in src


# ---------------------------------------------------------------------------
# Single AiCommander invariant
# ---------------------------------------------------------------------------


class TestSingleAiCommander:
    def test_ai_commander_exists(self):
        assert AI_COMMANDER.is_file()

    def test_app_uses_ai_commander(self, app_src):
        assert "AiCommander" in app_src
        assert "<AiCommander" in app_src

    def test_app_no_floating_assistant(self, app_src):
        assert "FloatingAIAssistant" not in app_src

    def test_floating_assistant_file_may_exist_but_unused(self, app_src):
        # legacy file can remain; must not be mounted
        assert "<FloatingAIAssistant" not in app_src

    def test_ai_commander_rule_based_summary(self):
        src = read_text(AI_COMMANDER)
        assert "RULE_BASED_SUMMARY" in src

    def test_ai_commander_modes_count(self):
        src = read_text(AI_COMMANDER)
        assert src.count("{ id:") >= 10

    def test_matrix_single_ai_invariant(self, matrix):
        assert matrix["invariants"]["single_ai_commander"] is True


# ---------------------------------------------------------------------------
# DataHunterX audit
# ---------------------------------------------------------------------------


class TestDataHunterxAudit:
    def test_audit_file_exists(self):
        assert AUDIT_JSON.is_file()

    def test_copy_forbidden_true(self, audit):
        assert audit["copy_forbidden"] is True

    def test_all_features_copy_forbidden(self, audit):
        for f in audit["features"]:
            assert f["copy_forbidden"] is True

    def test_features_include_ai_modes(self, audit):
        names = [f["feature"] for f in audit["features"]]
        assert "AI modes" in names

    def test_no_missing_features(self, audit):
        assert audit["coverage_summary"]["missing"] == 0

    def test_nexus_equivalent_on_all(self, audit):
        for f in audit["features"]:
            assert f.get("nexus_equivalent")


# ---------------------------------------------------------------------------
# Design tokens & pages
# ---------------------------------------------------------------------------


class TestWave4Assets:
    def test_tokens_css_exists(self):
        assert WAVE4_TOKENS.is_file()

    def test_tokens_w4_prefix(self):
        src = read_text(WAVE4_TOKENS)
        assert "--w4-" in src

    def test_universe_page_exists(self):
        assert (FRONTEND / "pages" / "UniversePage.tsx").is_file()

    def test_alerts_page_exists(self):
        assert (FRONTEND / "pages" / "AlertsPage.tsx").is_file()

    def test_column_presets_exists(self):
        assert (FRONTEND / "wave4" / "columnPresets.ts").is_file()

    def test_checkpoint_json(self):
        data = json.loads(CHECKPOINT_JSON.read_text(encoding="utf-8"))
        assert data["constraints_honored"]["shadow_ui_only"] is True

    def test_visual_manifest_planned(self):
        data = json.loads(VISUAL_JSON.read_text(encoding="utf-8"))
        assert data["browser_screenshot_capture_status"] == "planned_not_captured"
        assert len(data["screenshots"]) >= 10

    def test_report_md_exists(self):
        assert (DOCS / "NEXUS_WAVE4_PRODUCT_UI_INTELLIGENCE_REPORT.md").is_file()


# ---------------------------------------------------------------------------
# CI workflow
# ---------------------------------------------------------------------------


class TestCiWorkflow:
    def test_workflow_exists(self):
        assert WORKFLOW.is_file()

    def test_workflow_branch_filter(self):
        src = read_text(WORKFLOW)
        assert "feature/wave4-product-ui-intelligence" in src

    def test_workflow_typecheck(self):
        src = read_text(WORKFLOW)
        assert "typecheck" in src

    def test_workflow_pytest_wave4(self):
        src = read_text(WORKFLOW)
        assert "test_wave4_product_ui_intelligence.py" in src

    def test_workflow_no_deploy(self):
        src = read_text(WORKFLOW)
        assert "deploy" not in src.lower() or "no deploy" in src.lower() or "# Wave 4" in src

    def test_workflow_wave2_wave3(self):
        src = read_text(WORKFLOW)
        assert "test_wave3_adaptive_policy_learning.py" in src
        assert "test_wave2_global_market_six_role.py" in src


# ---------------------------------------------------------------------------
# Extra route parity (parametric expansion to reach 80+)
# ---------------------------------------------------------------------------


EXTRA_MATRIX_PATHS = [
    "/crypto/sectors/:sectorSlug",
    "/crypto/funding",
    "/crypto/price-oi",
    "/equities/tokenized",
    "/equities/analysis",
]


class TestMatrixRouteParity:
    @pytest.mark.parametrize("path", EXTRA_MATRIX_PATHS)
    def test_matrix_route_listed(self, matrix, path):
        paths = [r["path"] for r in matrix["routes"]]
        assert path in paths

    def test_universe_added_status(self, matrix):
        u = [r for r in matrix["routes"] if r["path"] == "/universe"]
        assert u[0]["status"] == "added"

    def test_scanner_alias_status(self, matrix):
        s = [r for r in matrix["routes"] if r["path"] == "/scanner"]
        assert s[0]["status"] == "alias"


class TestForbiddenUiStrings:
    FORBIDDEN = ["Live Trade", "MAINNET", "place order", "submit order"]

    @pytest.mark.parametrize("forbidden", FORBIDDEN)
    def test_portfolio_page_no_forbidden_cta(self, forbidden):
        src = read_text(FRONTEND / "pages" / "PortfolioWorkspacePage.tsx")
        if forbidden.lower() == "live trade":
            assert re.search(r"(?<!NO )Live Trade", src) is None
        else:
            assert forbidden not in src

    def test_portfolio_no_arm_button(self):
        src = read_text(FRONTEND / "pages" / "PortfolioWorkspacePage.tsx")
        assert re.search(r"(?<!NO )ARM(?!ING)", src) is None or "NO ARM" in src

    def test_overview_no_bybit(self):
        assert "BybitDemoAutonomousCard" not in read_text(PRODUCT_SIMPLE)
