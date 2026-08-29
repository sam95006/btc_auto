"""Central Personal product feature -> entitlement (+ optional quota) mapping.

Nothing in the product should scatter ``if plan == "pro"``. Feature access is
resolved here from the stable BILLING-2 entitlement codes and BILLING-6 quota
codes. The mapping is intentionally explicit and centralized.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.nexus_billing.usage_policy import (
    QUOTA_ANALYSIS_DAILY,
    QUOTA_HISTORY_DAYS,
    QUOTA_REPORTS_MONTHLY,
    QUOTA_WATCHLIST_ITEMS,
)

# Quota kinds a product feature can carry.
QUOTA_KIND_NONE = "none"
QUOTA_KIND_CONSUMABLE = "consumable"
QUOTA_KIND_CAPACITY = "capacity"


@dataclass(frozen=True)
class ProductFeature:
    key: str
    entitlement: str  # BILLING-2 feature code that gates this product feature
    label: str
    quota_code: Optional[str] = None
    quota_kind: str = QUOTA_KIND_NONE
    available: bool = True  # False = defined but no real backend yet (coming soon)


# Personal product feature catalog. Entitlement codes align with BILLING-2; the
# mapping stays centralized so routes/UI never hard-code plans.
PRODUCT_FEATURES: dict[str, ProductFeature] = {
    # Free
    "market_overview": ProductFeature("market_overview", "market_overview", "市場總覽"),
    "basic_market_data": ProductFeature("basic_market_data", "basic_market_data", "基礎市場資料"),
    "basic_alerts": ProductFeature("basic_alerts", "basic_alerts", "基礎提醒"),
    # Starter
    "market_intelligence": ProductFeature("market_intelligence", "market_intelligence", "市場情報"),
    "watchlists": ProductFeature(
        "watchlists", "watchlists", "觀察清單",
        quota_code=QUOTA_WATCHLIST_ITEMS, quota_kind=QUOTA_KIND_CAPACITY,
    ),
    "extended_market_history": ProductFeature(
        "extended_market_history", "extended_market_history", "延伸歷史資料",
        quota_code=QUOTA_HISTORY_DAYS, quota_kind=QUOTA_KIND_CAPACITY,
    ),
    # Pro
    "advanced_signals": ProductFeature("advanced_signals", "advanced_signals", "進階訊號"),
    "risk_intelligence": ProductFeature("risk_intelligence", "risk_intelligence", "風險情報"),
    "advanced_analysis": ProductFeature(
        "advanced_analysis", "advanced_analysis", "進階分析",
        quota_code=QUOTA_ANALYSIS_DAILY, quota_kind=QUOTA_KIND_CONSUMABLE,
    ),
    "report_generation": ProductFeature(
        "report_generation", "report_generation", "報告產生",
        quota_code=QUOTA_REPORTS_MONTHLY, quota_kind=QUOTA_KIND_CONSUMABLE,
    ),
    # Advanced (defined; real backends land incrementally -> availability flags)
    "premium_intelligence": ProductFeature("premium_intelligence", "premium_intelligence", "頂級情報", available=False),
    "higher_usage_limits": ProductFeature("higher_usage_limits", "higher_usage_limits", "更高用量上限", available=True),
    "advanced_data": ProductFeature("advanced_data", "advanced_data", "進階數據", available=False),
    "advanced_risk_analysis": ProductFeature("advanced_risk_analysis", "advanced_risk_analysis", "進階風險分析", available=False),
}


def get_feature(key: str) -> Optional[ProductFeature]:
    return PRODUCT_FEATURES.get(key)


def feature_entitlement(key: str) -> Optional[str]:
    feature = PRODUCT_FEATURES.get(key)
    return feature.entitlement if feature else None
