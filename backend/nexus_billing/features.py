"""Central feature catalog for BILLING-2.

Stable internal feature codes live here so routes/services never scatter
hard-coded feature strings. These are technical entitlement identifiers, not
marketing copy — display names and plan contents remain changeable elsewhere.
"""

from __future__ import annotations

from typing import Optional

# Logical feature groups by capability tier. These names are internal and
# stable; they are NOT final product/marketing names.
FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "free": (
        "market_overview",
        "basic_market_data",
        "basic_alerts",
    ),
    "starter": (
        "market_intelligence",
        "watchlists",
        "extended_market_history",
    ),
    "pro": (
        "advanced_signals",
        "risk_intelligence",
        "advanced_analysis",
        "report_generation",
    ),
    "advanced": (
        "premium_intelligence",
        "higher_usage_limits",
        "advanced_data",
        "advanced_risk_analysis",
    ),
    "enterprise": (
        "organization_features",
        "enterprise_agents",
        "enterprise_data",
        "enterprise_admin",
        "custom_limits",
    ),
}

# Deterministic, de-duplicated ordering (group order, then in-group order).
def _build_all_features() -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for group in ("free", "starter", "pro", "advanced", "enterprise"):
        for code in FEATURE_GROUPS[group]:
            if code not in seen:
                seen.add(code)
                ordered.append(code)
    return tuple(ordered)


ALL_FEATURES: tuple[str, ...] = _build_all_features()
FEATURE_SET: frozenset[str] = frozenset(ALL_FEATURES)


def is_valid_feature(code: Optional[str]) -> bool:
    return isinstance(code, str) and code in FEATURE_SET
