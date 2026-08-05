"""PUB2-J Pass 1 — foundation: zh-TW default, English parity, budgets, a11y assets."""

from __future__ import annotations

from pathlib import Path

from backend.nexus_public_a11y_i18n_perf import (
    DEFAULT_LOCALE,
    MIN_TOUCH_TARGET_PX,
    MOBILE_OVERFLOW_WIDTH_PX,
    PERFORMANCE_BUDGETS,
    SUPPORTED_LOCALES,
    WCAG_TARGET,
)
from backend.nexus_public_a11y_i18n_perf.hard_bans import scan_hard_bans
from backend.nexus_public_a11y_i18n_perf.i18n_parity import check_catalog_parity

REPO = Path(__file__).resolve().parents[2]


def test_default_locale_zh_tw():
    assert DEFAULT_LOCALE == "zh-TW"
    assert "en" in SUPPORTED_LOCALES


def test_wcag_target_and_touch():
    assert WCAG_TARGET == "WCAG_2_2_AA"
    assert MIN_TOUCH_TARGET_PX == 44
    assert MOBILE_OVERFLOW_WIDTH_PX == 375


def test_performance_budgets_defined():
    assert PERFORMANCE_BUDGETS["max_entry_js_bytes"] <= 450_000
    assert PERFORMANCE_BUDGETS["max_total_js_bytes"] <= 900_000


def test_owned_frontend_assets_exist():
    required = [
        "frontend/src/i18n/catalog.ts",
        "frontend/src/i18n/messages/zh-TW.ts",
        "frontend/src/i18n/messages/en.ts",
        "frontend/src/styles/a11yPerf.css",
        "frontend/src/perf/budgets.ts",
        "frontend/e2e/a11y-member.spec.ts",
        "frontend/index.html",
    ]
    for rel in required:
        assert (REPO / rel).is_file(), rel


def test_index_html_zh_default():
    html = (REPO / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'lang="zh-Hant-TW"' in html


def test_catalog_parity():
    result = check_catalog_parity()
    assert result["ok"], result


def test_hard_ban_pass1():
    result = scan_hard_bans(1)
    assert result["ok"], result
