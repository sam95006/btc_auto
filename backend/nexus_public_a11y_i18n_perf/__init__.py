"""PUB2-J accessibility, localization, and performance foundation."""

from __future__ import annotations

HARD_BANS: tuple[str, ...] = (
    "no_pr26_pr27_merge",
    "no_private_core_leak",
    "no_exchange_write",
    "no_demo_shadow_mainnet_trading",
    "no_live_billing",
    "no_fabricated_customers_or_metrics",
    "no_human_facing_status_json",
    "no_final_acceleration_report_edit",
)

DEFAULT_LOCALE = "zh-TW"
SUPPORTED_LOCALES: tuple[str, ...] = ("zh-TW", "en")

# Mirrored from frontend/src/perf/budgets.ts
PERFORMANCE_BUDGETS: dict[str, int] = {
    "max_entry_js_bytes": 450_000,
    "max_total_js_bytes": 900_000,
    "max_total_css_bytes": 220_000,
    "max_index_html_bytes": 12_000,
}

MIN_TOUCH_TARGET_PX = 44
MOBILE_OVERFLOW_WIDTH_PX = 375
WCAG_TARGET = "WCAG_2_2_AA"
