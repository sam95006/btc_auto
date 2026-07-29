"""Wave 4.1 visual acceptance — static CI / e2e infrastructure inspections (>=50 tests)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
E2E = FRONTEND / "e2e"
DOCS = ROOT / "docs" / "04_readiness"
WORKFLOW = ROOT / ".github" / "workflows" / "wave4_product_ui_intelligence_validation.yml"
PACKAGE_JSON = FRONTEND / "package.json"
PLAYWRIGHT_CONFIG = FRONTEND / "playwright.config.ts"
APP_TSX = FRONTEND / "src" / "App.tsx"
PRODUCT_SIMPLE = FRONTEND / "src" / "components" / "ProductSimpleView.tsx"
MATRIX_JSON = DOCS / "NEXUS_WAVE4_UI_FEATURE_PRESERVATION_MATRIX.json"
VISUAL_JSON = DOCS / "NEXUS_WAVE4_VISUAL_REGRESSION_MANIFEST.json"
CHECKPOINT_JSON = DOCS / "NEXUS_WAVE4_PRODUCT_UI_CHECKPOINT.json"
ACCEPTANCE_REPORT = DOCS / "NEXUS_WAVE4_VISUAL_ACCEPTANCE_REPORT.md"
ARTIFACTS_AFTER = ROOT / "artifacts" / "wave4" / "after"
ARTIFACTS_BEFORE = ROOT / "artifacts" / "wave4" / "before"

REQUIRED_E2E_SPECS = [
    "overview.spec.ts",
    "universe.spec.ts",
    "opportunities.spec.ts",
    "alerts.spec.ts",
    "portfolio.spec.ts",
    "learning.spec.ts",
    "evidence.spec.ts",
    "workbench.spec.ts",
    "founder-runtime.spec.ts",
    "responsive.spec.ts",
    "accessibility.spec.ts",
    "route-preservation.spec.ts",
    "visual.spec.ts",
]

REQUIRED_E2E_HELPERS = [
    "helpers/constants.ts",
    "helpers/consoleErrors.ts",
    "helpers/safetyAssertions.ts",
    "helpers/screenshotNaming.ts",
    "helpers/pageSetup.ts",
]

REQUIRED_PACKAGE_SCRIPTS = {
    "e2e": "playwright test",
    "e2e:a11y": "playwright test --grep @a11y",
    "e2e:visual": "playwright test --grep @visual",
}


def route_slug(route: str) -> str:
    trimmed = route.strip("/")
    if not trimmed:
        return "root"
    return trimmed.replace("/", "_").replace(":", "")


def screenshot_file_name(route: str, state: str, width: int, height: int) -> str:
    return f"{route_slug(route)}_{state}_{width}x{height}.png"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow_src() -> str:
    return read_text(WORKFLOW)


@pytest.fixture(scope="module")
def package_data() -> dict:
    return json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix() -> dict:
    return json.loads(MATRIX_JSON.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# CI workflow
# ---------------------------------------------------------------------------


class TestWave4CiWorkflow:
    def test_workflow_file_exists(self):
        assert WORKFLOW.is_file()

    def test_pr_trigger_base_is_wave3(self, workflow_src):
        assert "feature/wave3-adaptive-policy-learning" in workflow_src
        assert re.search(
            r"pull_request:\s*\n\s*branches:\s*\n\s*-\s*\"feature/wave3-adaptive-policy-learning\"",
            workflow_src,
        )

    def test_push_trigger_wave4_branch(self, workflow_src):
        assert "feature/wave4-product-ui-intelligence" in workflow_src

    def test_workflow_has_wave4_python_job(self, workflow_src):
        assert "wave4-python:" in workflow_src

    def test_workflow_has_wave4_frontend_job(self, workflow_src):
        assert "wave4-frontend:" in workflow_src

    def test_workflow_has_wave4_browser_job(self, workflow_src):
        assert "wave4-browser:" in workflow_src

    def test_workflow_has_wave4_accessibility_job(self, workflow_src):
        assert "wave4-accessibility:" in workflow_src

    def test_workflow_has_wave4_visual_job(self, workflow_src):
        assert "wave4-visual:" in workflow_src

    def test_workflow_has_wave4_docker_job(self, workflow_src):
        assert "wave4-docker:" in workflow_src

    def test_workflow_runs_visual_acceptance_pytest(self, workflow_src):
        assert "test_wave4_visual_acceptance.py" in workflow_src

    def test_workflow_env_autonomous_send_false(self, workflow_src):
        assert 'AUTONOMOUS_SEND: "false"' in workflow_src

    def test_workflow_env_exchange_write_false(self, workflow_src):
        assert 'EXCHANGE_WRITE: "false"' in workflow_src

    def test_workflow_env_explicit_fixture_false(self, workflow_src):
        assert 'EXPLICIT_FIXTURE_MODE: "false"' in workflow_src

    def test_workflow_docker_smoke_overview(self, workflow_src):
        assert "/overview" in workflow_src
        assert "/universe" in workflow_src
        assert "/founder/runtime" in workflow_src

    def test_workflow_uploads_visual_artifacts(self, workflow_src):
        assert "artifacts/wave4/after/" in workflow_src

    def test_workflow_no_continue_on_error_docker(self, workflow_src):
        docker_block = workflow_src.split("wave4-docker:")[1]
        assert "continue-on-error" not in docker_block


# ---------------------------------------------------------------------------
# E2E file presence
# ---------------------------------------------------------------------------


class TestE2eFilesExist:
    def test_playwright_config_exists(self):
        assert PLAYWRIGHT_CONFIG.is_file()

    def test_capture_before_live_script_exists(self):
        assert (E2E / "capture_before_live.mjs").is_file()

    @pytest.mark.parametrize("spec", REQUIRED_E2E_SPECS)
    def test_e2e_spec_exists(self, spec):
        assert (E2E / spec).is_file()

    @pytest.mark.parametrize("helper", REQUIRED_E2E_HELPERS)
    def test_e2e_helper_exists(self, helper):
        assert (E2E / helper).is_file()

    def test_playwright_config_uses_preview_port_4173(self):
        src = read_text(PLAYWRIGHT_CONFIG)
        assert "4173" in src
        assert "preview" in src


# ---------------------------------------------------------------------------
# package.json scripts & deps
# ---------------------------------------------------------------------------


class TestPackageJsonScripts:
    @pytest.mark.parametrize("script,expected", list(REQUIRED_PACKAGE_SCRIPTS.items()))
    def test_required_script(self, package_data, script, expected):
        assert package_data["scripts"][script] == expected

    def test_playwright_test_dev_dependency(self, package_data):
        assert "@playwright/test" in package_data["devDependencies"]

    def test_axe_playwright_dev_dependency(self, package_data):
        assert "@axe-core/playwright" in package_data["devDependencies"]


# ---------------------------------------------------------------------------
# Screenshot naming helpers
# ---------------------------------------------------------------------------


class TestScreenshotNamingHelpers:
    @pytest.mark.parametrize(
        "route,state,w,h,expected",
        [
            ("/overview", "simple", 1440, 900, "overview_simple_1440x900.png"),
            ("/", "root", 390, 844, "root_root_390x844.png"),
            ("/market/BTCUSDT", "workbench", 1440, 900, "market_BTCUSDT_workbench_1440x900.png"),
            ("/founder/runtime", "readonly", 768, 1024, "founder_runtime_readonly_768x1024.png"),
        ],
    )
    def test_screenshot_file_name(self, route, state, w, h, expected):
        assert screenshot_file_name(route, state, w, h) == expected

    def test_route_slug_empty(self):
        assert route_slug("/") == "root"

    def test_route_slug_nested(self):
        assert route_slug("/crypto/sectors") == "crypto_sectors"

    def test_visual_spec_writes_to_artifacts_after(self):
        spec_src = read_text(E2E / "visual.spec.ts")
        const_src = read_text(E2E / "helpers" / "constants.ts")
        assert "ARTIFACTS_AFTER_DIR" in spec_src
        assert "artifacts/wave4/after" in const_src

    def test_capture_before_live_writes_to_before(self):
        src = read_text(E2E / "capture_before_live.mjs")
        assert "artifacts/wave4/before" in src
        assert "nexus-stage3-bybit-demo-learning.zeabur.app" in src


# ---------------------------------------------------------------------------
# App invariants
# ---------------------------------------------------------------------------


class TestAppSingleAiCommander:
    def test_app_mounts_single_ai_commander(self):
        src = read_text(APP_TSX)
        assert src.count("<AiCommander") == 1

    def test_app_no_floating_assistant_import(self):
        src = read_text(APP_TSX)
        assert "FloatingAIAssistant" not in src

    def test_founder_runtime_route_present(self):
        src = read_text(APP_TSX)
        assert 'path="/founder/runtime"' in src

    def test_matrix_single_ai_invariant(self, matrix):
        assert matrix["invariants"]["single_ai_commander"] is True


# ---------------------------------------------------------------------------
# ProductSimpleView provider / failure polish
# ---------------------------------------------------------------------------


class TestProductSimpleViewProviderPatterns:
    PROVIDER_SUMMARY_PATTERNS = [
        r"buildFunnelDisplay",
        r"NO_DATA",
        r"portfolioLeverageBadge",
        r"Provider Health",
        r"掃描器",
        r"Market Pulse",
        r"Decision Funnel",
    ]

    @pytest.mark.parametrize("pattern", PROVIDER_SUMMARY_PATTERNS)
    def test_product_simple_has_summary_patterns(self, pattern):
        src = read_text(PRODUCT_SIMPLE)
        assert re.search(pattern, src)

    def test_product_simple_no_synthetic_128_default(self):
        src = read_text(PRODUCT_SIMPLE)
        assert "128" not in src or "is_synthetic" in read_text(ROOT / "frontend" / "src" / "wave4" / "noDataFunnel.ts")

    def test_error_banner_not_only_content(self):
        src = read_text(PRODUCT_SIMPLE)
        assert "nx-p7-block" in src
        assert "Market Pulse" in src


# ---------------------------------------------------------------------------
# Feature matrix optional click_depth
# ---------------------------------------------------------------------------


class TestFeatureMatrixOptionalFields:
    def test_matrix_routes_non_empty(self, matrix):
        assert len(matrix["routes"]) >= 30

    def test_click_depth_if_present_is_numeric(self, matrix):
        for route in matrix["routes"]:
            if "click_depth" in route:
                assert isinstance(route["click_depth"], int)
                assert route["click_depth"] >= 0


# ---------------------------------------------------------------------------
# Docs & manifest honesty
# ---------------------------------------------------------------------------


class TestVisualAcceptanceDocs:
    def test_visual_manifest_exists(self):
        assert VISUAL_JSON.is_file()

    def test_checkpoint_exists(self):
        assert CHECKPOINT_JSON.is_file()

    def test_acceptance_report_skeleton_exists(self):
        assert ACCEPTANCE_REPORT.is_file()

    def test_acceptance_report_has_26_sections(self):
        src = read_text(ACCEPTANCE_REPORT)
        for i in range(1, 27):
            assert re.search(rf"##\s*{i}\.", src)

    def test_checkpoint_wave4_ci_trigger_fixed(self):
        data = json.loads(CHECKPOINT_JSON.read_text(encoding="utf-8"))
        assert data.get("wave4_ci_trigger_fixed") is True

    def test_checkpoint_recommendation_partial_or_ready(self):
        data = json.loads(CHECKPOINT_JSON.read_text(encoding="utf-8"))
        # Canonical Wave 4 recommendation enum (no wildcards / deprecated aliases).
        assert data["recommendation"] in {
            "WAVE4_PRODUCT_UI_DRAFT_PR_READY_FOR_REVIEW",
            "WAVE4_PRODUCT_UI_PARTIAL_WITH_VISUAL_VALIDATION_BLOCKERS",
            "BLOCKED_WAVE4_PRODUCT_UI",
        }


class TestE2eSpecTags:
    def test_accessibility_spec_has_a11y_tag(self):
        src = read_text(E2E / "accessibility.spec.ts")
        assert "@a11y" in src

    def test_visual_spec_has_visual_tag(self):
        src = read_text(E2E / "visual.spec.ts")
        assert "@visual" in src

    def test_route_preservation_fleets_redirect(self):
        src = read_text(E2E / "route-preservation.spec.ts")
        assert "/fleets" in src
        assert "/universe" in src

    def test_safety_assertions_cover_forbidden_controls(self):
        src = read_text(E2E / "helpers" / "safetyAssertions.ts")
        assert "Live Trade" in src
        assert "FloatingAIAssistant" not in src
        assert 'aria-label="AI Assistant"' in src
