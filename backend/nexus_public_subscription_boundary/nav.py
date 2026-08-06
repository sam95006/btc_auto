"""Web / mobile navigation product boundary helpers."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_subscription_boundary.constants import (
    MEMBER_ALLOWED_NAV_PRODUCTS,
    MEMBER_BUYABLE_PRODUCT_IDS,
    MEMBER_FORBIDDEN_PRODUCT_IDS,
)
from backend.nexus_public_subscription_boundary.hard_bans import (
    HardBanViolation,
    assert_no_forbidden_in_iterable,
    normalize_product_id,
)

# Canonical member web nav → product_id mapping (intelligence products only).
WEB_NAV_PRODUCT_MAP: dict[str, str] = {
    "/home": "home",
    "/market": "market_data",
    "/intelligence": "ai_intelligence",
    "/decisions": "decision_context",
    "/evidence": "evidence",
    "/counter-evidence": "counter_evidence",
    "/risk-conditions": "risk_explanation",
    "/thesis-monitor": "thesis_monitor",
    "/alerts": "alerts",
    "/decision-memory": "decision_memory",
    "/outcome-review": "outcome_review",
    "/nex-ai": "ai_intelligence",
    "/membership": "membership",
    "/account": "account",
    "/privacy": "privacy",
    "/account-deletion": "account_deletion",
    "/notification-settings": "notification_settings",
    "/historical-comparisons": "historical_comparisons",
    "/global-briefs": "global_market_briefs",
}

# Paths that must NEVER appear in member navigation.
FORBIDDEN_WEB_NAV_PATHS: frozenset[str] = frozenset(
    {
        "/auto-trading",
        "/copy-trading",
        "/exchange-execution",
        "/private-strategy",
        "/founder-portfolio",
        "/execution",
        "/trade",
        "/place-order",
    }
)

MOBILE_NAV_PRODUCT_MAP: dict[str, str] = {
    "/": "home",
    "/markets": "market_data",
    "/decisions": "decision_context",
    "/evidence": "evidence",
    "/risks": "risk_explanation",
    "/alerts": "alerts",
    "/memory": "decision_memory",
    "/outcome": "outcome_review",
    "/nex-ai": "ai_intelligence",
    "/membership": "membership",
    "/account": "account",
    "/privacy": "privacy",
    "/notifications": "notification_settings",
    "/historical-comparisons": "historical_comparisons",
    "/global-briefs": "global_market_briefs",
}

FORBIDDEN_MOBILE_NAV_ROUTES: frozenset[str] = frozenset(
    {
        "/auto-trading",
        "/copy-trading",
        "/exchange-execution",
        "/private-strategy",
        "/founder-portfolio",
        "/execution",
        "/trade",
    }
)


def assert_web_nav_clean(paths: list[str]) -> None:
    for path in paths:
        if path in FORBIDDEN_WEB_NAV_PATHS:
            raise HardBanViolation(
                f"HARD BAN: member web nav includes forbidden path {path!r}"
            )
        product = WEB_NAV_PRODUCT_MAP.get(path)
        if product is None:
            continue
        pid = normalize_product_id(product)
        if pid in MEMBER_FORBIDDEN_PRODUCT_IDS:
            raise HardBanViolation(
                f"HARD BAN: member web nav maps {path!r} to forbidden product {pid!r}"
            )
        if pid not in MEMBER_ALLOWED_NAV_PRODUCTS and pid not in MEMBER_BUYABLE_PRODUCT_IDS:
            raise HardBanViolation(
                f"HARD BAN: member web nav product {pid!r} not allowed"
            )


def assert_mobile_nav_clean(routes: list[str]) -> None:
    for route in routes:
        if route in FORBIDDEN_MOBILE_NAV_ROUTES:
            raise HardBanViolation(
                f"HARD BAN: member mobile nav includes forbidden route {route!r}"
            )
        product = MOBILE_NAV_PRODUCT_MAP.get(route)
        if product is None:
            continue
        pid = normalize_product_id(product)
        assert_no_forbidden_in_iterable([pid], context=f"mobile_nav:{route}")


def member_web_nav_snapshot(paths: list[str]) -> dict[str, Any]:
    assert_web_nav_clean(paths)
    products = [WEB_NAV_PRODUCT_MAP[p] for p in paths if p in WEB_NAV_PRODUCT_MAP]
    assert_no_forbidden_in_iterable(products, context="web_nav_products")
    return {
        "paths": list(paths),
        "products": products,
        "forbidden_paths_present": [],
        "execution_controls": False,
    }


def member_mobile_nav_snapshot(routes: list[str]) -> dict[str, Any]:
    assert_mobile_nav_clean(routes)
    products = [MOBILE_NAV_PRODUCT_MAP[r] for r in routes if r in MOBILE_NAV_PRODUCT_MAP]
    assert_no_forbidden_in_iterable(products, context="mobile_nav_products")
    return {
        "routes": list(routes),
        "products": products,
        "forbidden_routes_present": [],
        "execution_controls": False,
    }
