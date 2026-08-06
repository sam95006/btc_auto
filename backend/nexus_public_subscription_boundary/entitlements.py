"""Product-level entitlements for PUB17-D (no live billing).

Maps Free/Pro/Elite/Enterprise tiers to buyable intelligence products only.
Never grants MEMBER_FORBIDDEN_PRODUCTS or execution controls.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_public_subscription_boundary.constants import (
    BILLING_PROVIDER,
    LIVE_BILLING_ENABLED,
    MEMBER_BUYABLE_PRODUCT_IDS,
    MEMBER_FORBIDDEN_PRODUCT_IDS,
)
from backend.nexus_public_subscription_boundary.hard_bans import (
    HardBanViolation,
    assert_buyable_catalog_clean,
    assert_no_forbidden_in_iterable,
    is_forbidden_product,
    refuse_forbidden_product,
    refuse_live_billing,
)

# Tier → buyable product ids (subset of MEMBER_BUYABLE_PRODUCT_IDS only).
TIER_PRODUCTS: dict[str, frozenset[str]] = {
    "Free": frozenset({"market_data", "decision_context", "risk_explanation"}),
    "Pro": frozenset(
        {
            "market_data",
            "ai_intelligence",
            "decision_context",
            "risk_explanation",
            "alerts",
            "historical_comparisons",
        }
    ),
    "Elite": frozenset(MEMBER_BUYABLE_PRODUCT_IDS),
    "Enterprise": frozenset(MEMBER_BUYABLE_PRODUCT_IDS),
}

TIER_PRODUCTS_FINGERPRINT = {
    tier: tuple(sorted(products)) for tier, products in TIER_PRODUCTS.items()
}


def _assert_matrix_clean() -> None:
    for tier, products in TIER_PRODUCTS.items():
        assert_buyable_catalog_clean(products)
        overlap = products & MEMBER_FORBIDDEN_PRODUCT_IDS
        if overlap:
            raise HardBanViolation(
                f"HARD BAN: tier {tier} grants forbidden products: {sorted(overlap)}"
            )


_assert_matrix_clean()


def assert_tier_products_immutable() -> None:
    for tier, expected in TIER_PRODUCTS_FINGERPRINT.items():
        current = TIER_PRODUCTS.get(tier)
        if current is None or tuple(sorted(current)) != expected:
            raise HardBanViolation(
                f"HARD BAN: tier product matrix for {tier} mutated at runtime"
            )
        assert_no_forbidden_in_iterable(current, context=f"tier={tier}")


def products_for_tier(tier: str) -> frozenset[str]:
    if tier not in TIER_PRODUCTS:
        raise HardBanViolation(f"unknown membership tier {tier!r}")
    assert_tier_products_immutable()
    products = TIER_PRODUCTS[tier]
    assert_no_forbidden_in_iterable(products, context=f"tier={tier}")
    return products


def has_product(tier: str, product_id: str) -> bool:
    refuse_forbidden_product(product_id)
    if is_forbidden_product(product_id):
        return False
    return product_id in products_for_tier(tier)


def require_product(tier: str, product_id: str) -> None:
    refuse_forbidden_product(product_id)
    if not has_product(tier, product_id):
        raise HardBanViolation(
            f"entitlement denied: tier={tier} missing product={product_id}"
        )


def grant_product_manual(
    *,
    tier: str,
    product_id: str,
    actor: str,
) -> dict[str, Any]:
    """Non-production manual grant. Never grants forbidden / execution products."""
    if LIVE_BILLING_ENABLED or BILLING_PROVIDER != "NONE_NON_PRODUCTION":
        refuse_live_billing()
    if actor.startswith("stripe:") or actor.startswith("iap:"):
        refuse_live_billing()
    refuse_forbidden_product(product_id)
    require_product(tier, product_id)
    return {
        "tier": tier,
        "product_id": product_id,
        "granted": True,
        "live_billing_enabled": False,
        "billing_provider": BILLING_PROVIDER,
        "assignment_mode": "manual_non_production",
        "actor": actor,
        "execution_controls": False,
        "forbidden_products_granted": [],
    }


def entitlement_product_snapshot(tier: str) -> dict[str, Any]:
    products = products_for_tier(tier)
    return {
        "tier": tier,
        "buyable_products": sorted(products),
        "forbidden_products": sorted(MEMBER_FORBIDDEN_PRODUCT_IDS),
        "live_billing_enabled": False,
        "billing_provider": BILLING_PROVIDER,
        "execution_controls": False,
        "member_execution_control_count": 0,
    }
