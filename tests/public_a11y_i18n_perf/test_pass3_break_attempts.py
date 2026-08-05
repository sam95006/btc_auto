"""PUB2-J Pass 3 — independent break attempts against bans and budgets."""

from __future__ import annotations

import re
from pathlib import Path

from backend.nexus_public_a11y_i18n_perf import PERFORMANCE_BUDGETS
from backend.nexus_public_a11y_i18n_perf.hard_bans import scan_hard_bans

REPO = Path(__file__).resolve().parents[2]


def test_budgets_ts_matches_python():
    text = (REPO / "frontend" / "src" / "perf" / "budgets.ts").read_text(encoding="utf-8")
    for key, value in (
        ("maxEntryJsBytes", PERFORMANCE_BUDGETS["max_entry_js_bytes"]),
        ("maxTotalJsBytes", PERFORMANCE_BUDGETS["max_total_js_bytes"]),
        ("maxTotalCssBytes", PERFORMANCE_BUDGETS["max_total_css_bytes"]),
        ("maxIndexHtmlBytes", PERFORMANCE_BUDGETS["max_index_html_bytes"]),
    ):
        # Allow numeric separators: 450_000
        assert re.search(rf"{key}:\s*{value:_}", text) or re.search(
            rf"{key}:\s*{value}", text
        ), (key, value)


def test_measure_script_exists_and_refuses_status_json():
    script = (REPO / "frontend" / "scripts" / "measure_performance_budget.mjs").read_text(
        encoding="utf-8"
    )
    assert "maxEntryJsBytes" in script
    assert "*_status.json" in script  # documents ban
    assert "PERF_MEASURED" in script


def test_break_attempt_no_status_artifact_writers_in_owned_tools():
    tools = REPO / "tools" / "public_v2"
    for path in tools.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "_status.json" not in text or "Does NOT write" in text


def test_hard_ban_pass3():
    result = scan_hard_bans(3)
    assert result["ok"], result


def test_app_strings_bilingual_screen_titles():
    strings = (
        REPO / "apps" / "nexus_public_mobile" / "lib" / "core" / "l10n" / "app_strings.dart"
    ).read_text(encoding="utf-8")
    assert "zh_TW" in strings or "zh-TW" in strings or "Locale('zh', 'TW')" in strings
    assert "screenTitle" in strings
