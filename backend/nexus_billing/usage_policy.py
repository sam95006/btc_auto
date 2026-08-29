"""Central usage-quota policy for BILLING-6.

Two distinct layers (do not merge them):
  * Entitlement (BILLING-2): does the plan HAVE this feature?
  * Usage quota (here): once entitled, HOW MUCH may be used?

All quota values below are TECHNICAL PREVIEW / CONFIGURABLE — they are NOT final
commercial commitments and may change without touching feature codes or schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Stable internal quota codes.
QUOTA_ANALYSIS_DAILY = "advanced_analysis_requests_daily"
QUOTA_REPORTS_MONTHLY = "report_generation_monthly"
QUOTA_WATCHLIST_ITEMS = "watchlist_items"
QUOTA_HISTORY_DAYS = "history_days"

# Window types.
WINDOW_DAILY = "daily"
WINDOW_MONTHLY = "monthly"
WINDOW_NONE = "none"

# Quota value types.
TYPE_CONSUMABLE = "consumable"  # increments with use, needs a usage ledger
TYPE_CAPACITY = "capacity"      # a static ceiling, no consumption ledger


@dataclass(frozen=True)
class QuotaSpec:
    code: str
    quota_type: str
    window: str
    entitlement: str  # the BILLING-2 feature that gates this quota
    label: str


QUOTA_CATALOG: dict[str, QuotaSpec] = {
    QUOTA_ANALYSIS_DAILY: QuotaSpec(
        QUOTA_ANALYSIS_DAILY, TYPE_CONSUMABLE, WINDOW_DAILY, "advanced_analysis", "AI 分析（每日）"
    ),
    QUOTA_REPORTS_MONTHLY: QuotaSpec(
        QUOTA_REPORTS_MONTHLY, TYPE_CONSUMABLE, WINDOW_MONTHLY, "report_generation", "報告產生（每月）"
    ),
    QUOTA_WATCHLIST_ITEMS: QuotaSpec(
        QUOTA_WATCHLIST_ITEMS, TYPE_CAPACITY, WINDOW_NONE, "watchlists", "觀察清單項目"
    ),
    QUOTA_HISTORY_DAYS: QuotaSpec(
        QUOTA_HISTORY_DAYS, TYPE_CAPACITY, WINDOW_NONE, "extended_market_history", "歷史資料天數"
    ),
}

# Plan -> {quota_code: limit}. TECHNICAL PREVIEW / CONFIGURABLE values.
_PLAN_QUOTAS: dict[str, dict[str, int]] = {
    "free": {
        QUOTA_ANALYSIS_DAILY: 0,
        QUOTA_REPORTS_MONTHLY: 0,
        QUOTA_WATCHLIST_ITEMS: 5,
        QUOTA_HISTORY_DAYS: 7,
    },
    "starter": {
        QUOTA_ANALYSIS_DAILY: 20,
        QUOTA_REPORTS_MONTHLY: 2,
        QUOTA_WATCHLIST_ITEMS: 20,
        QUOTA_HISTORY_DAYS: 30,
    },
    "pro": {
        QUOTA_ANALYSIS_DAILY: 100,
        QUOTA_REPORTS_MONTHLY: 20,
        QUOTA_WATCHLIST_ITEMS: 50,
        QUOTA_HISTORY_DAYS: 180,
    },
    "advanced": {
        QUOTA_ANALYSIS_DAILY: 500,
        QUOTA_REPORTS_MONTHLY: 100,
        QUOTA_WATCHLIST_ITEMS: 200,
        QUOTA_HISTORY_DAYS: 365,
    },
    "enterprise": {
        QUOTA_ANALYSIS_DAILY: 5000,
        QUOTA_REPORTS_MONTHLY: 1000,
        QUOTA_WATCHLIST_ITEMS: 1000,
        QUOTA_HISTORY_DAYS: 1095,
    },
}


def is_valid_quota(code: Optional[str]) -> bool:
    return isinstance(code, str) and code in QUOTA_CATALOG


def get_quota_spec(code: str) -> Optional[QuotaSpec]:
    return QUOTA_CATALOG.get(code)


def plan_quota_codes(plan_code: str) -> list[str]:
    # Deterministic order matching the catalog declaration.
    limits = _PLAN_QUOTAS.get(plan_code) or _PLAN_QUOTAS["free"]
    return [code for code in QUOTA_CATALOG if code in limits]


def quota_limit(plan_code: str, quota_code: str) -> Optional[int]:
    """The limit for a plan+quota, or None when the plan does not define it
    (unknown plan falls back to free)."""
    plan = plan_code if plan_code in _PLAN_QUOTAS else "free"
    return _PLAN_QUOTAS[plan].get(quota_code)
