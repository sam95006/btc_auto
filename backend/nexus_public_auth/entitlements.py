"""Free / Pro / Elite / Enterprise entitlement matrix (no live billing)."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_auth.constants import (
    BILLING_PROVIDER,
    LIVE_BILLING_ENABLED,
    MEMBERSHIP_TIERS,
    TIER_FEATURES,
)
from backend.nexus_public_auth.hard_bans import HardBanViolation, refuse_live_billing


def assert_valid_tier(tier: str) -> str:
    if tier not in MEMBERSHIP_TIERS:
        raise HardBanViolation(
            f"unknown membership tier {tier!r}; allowed={list(MEMBERSHIP_TIERS)}"
        )
    return tier


def features_for_tier(tier: str) -> frozenset[str]:
    assert_valid_tier(tier)
    return TIER_FEATURES[tier]


def has_feature(tier: str, feature: str) -> bool:
    return feature in features_for_tier(tier)


def require_feature(tier: str, feature: str) -> None:
    if not has_feature(tier, feature):
        raise HardBanViolation(
            f"entitlement denied: tier={tier} missing feature={feature}"
        )


def assign_tier_manual(*, current_tier: str, target_tier: str, actor: str) -> dict[str, Any]:
    """
    Non-production entitlement change.

    No payment provider, no IAP, no invoice. Operator/manual only.
    """
    if LIVE_BILLING_ENABLED or BILLING_PROVIDER != "NONE_NON_PRODUCTION":
        refuse_live_billing()
    assert_valid_tier(current_tier)
    assert_valid_tier(target_tier)
    if actor.startswith("stripe:") or actor.startswith("iap:"):
        refuse_live_billing()
    return {
        "from_tier": current_tier,
        "to_tier": target_tier,
        "billing_provider": BILLING_PROVIDER,
        "live_billing_enabled": False,
        "assignment_mode": "manual_non_production",
        "actor": actor,
        "features": sorted(features_for_tier(target_tier)),
    }


def entitlement_snapshot(tier: str) -> dict[str, Any]:
    assert_valid_tier(tier)
    return {
        "tier": tier,
        "features": sorted(features_for_tier(tier)),
        "billing_provider": BILLING_PROVIDER,
        "live_billing_enabled": LIVE_BILLING_ENABLED,
        "upgrade_path": "manual_non_production_only",
    }
