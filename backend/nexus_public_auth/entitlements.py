"""Free / Pro / Elite / Enterprise entitlement matrix (no live billing).

Entitlements MUST NEVER grant private execution access — any feature in
PRIVATE_EXECUTION_FEATURE_DENYLIST is refused for every tier.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_public_auth.constants import (
    BILLING_PROVIDER,
    LIVE_BILLING_ENABLED,
    MEMBERSHIP_TIERS,
    PRIVATE_EXECUTION_FEATURE_DENYLIST,
    TIER_FEATURES,
)
from backend.nexus_public_auth.hard_bans import HardBanViolation, refuse_live_billing


def assert_valid_tier(tier: str) -> str:
    if tier not in MEMBERSHIP_TIERS:
        raise HardBanViolation(
            f"unknown membership tier {tier!r}; allowed={list(MEMBERSHIP_TIERS)}"
        )
    return tier


def assert_not_private_execution_feature(feature: str) -> None:
    normalized = str(feature or "").strip().lower()
    if normalized in PRIVATE_EXECUTION_FEATURE_DENYLIST:
        raise HardBanViolation(
            f"HARD BAN: entitlement must never grant private execution access "
            f"(feature={feature!r})"
        )
    # Heuristic: any feature name that looks like private execution is refused.
    markers = (
        "private_execution",
        "exchange_write",
        "order_placement",
        "live_trading",
        "mainnet",
        "autonomy_control",
        "founder_operator",
        "checkpoint_mutate",
        "wallet_custody",
        "copy_trading",
    )
    if any(m in normalized for m in markers):
        raise HardBanViolation(
            f"HARD BAN: entitlement must never grant private execution access "
            f"(feature={feature!r})"
        )


def _assert_tier_matrix_clean() -> None:
    for tier, features in TIER_FEATURES.items():
        overlap = features & PRIVATE_EXECUTION_FEATURE_DENYLIST
        if overlap:
            raise HardBanViolation(
                f"HARD BAN: tier {tier} illegally includes private execution "
                f"features: {sorted(overlap)}"
            )


# Fail closed at import if matrix is corrupted.
_assert_tier_matrix_clean()


def features_for_tier(tier: str) -> frozenset[str]:
    assert_valid_tier(tier)
    features = TIER_FEATURES[tier]
    overlap = features & PRIVATE_EXECUTION_FEATURE_DENYLIST
    if overlap:
        raise HardBanViolation(
            f"HARD BAN: tier {tier} illegally includes private execution "
            f"features: {sorted(overlap)}"
        )
    return features


def has_feature(tier: str, feature: str) -> bool:
    assert_not_private_execution_feature(feature)
    return feature in features_for_tier(tier)


def require_feature(tier: str, feature: str) -> None:
    assert_not_private_execution_feature(feature)
    if not has_feature(tier, feature):
        raise HardBanViolation(
            f"entitlement denied: tier={tier} missing feature={feature}"
        )


def assign_tier_manual(*, current_tier: str, target_tier: str, actor: str) -> dict[str, Any]:
    """
    Non-production entitlement change.

    No payment provider, no IAP, no invoice. Operator/manual only.
    Never grants private execution capabilities.
    """
    if LIVE_BILLING_ENABLED or BILLING_PROVIDER != "NONE_NON_PRODUCTION":
        refuse_live_billing()
    assert_valid_tier(current_tier)
    assert_valid_tier(target_tier)
    if actor.startswith("stripe:") or actor.startswith("iap:"):
        refuse_live_billing()
    features = features_for_tier(target_tier)
    for feature in features:
        assert_not_private_execution_feature(feature)
    return {
        "from_tier": current_tier,
        "to_tier": target_tier,
        "billing_provider": BILLING_PROVIDER,
        "live_billing_enabled": False,
        "assignment_mode": "manual_non_production",
        "actor": actor,
        "features": sorted(features),
        "private_execution_access": False,
        "private_execution_features_granted": [],
    }


def entitlement_snapshot(tier: str) -> dict[str, Any]:
    assert_valid_tier(tier)
    features = features_for_tier(tier)
    return {
        "tier": tier,
        "features": sorted(features),
        "billing_provider": BILLING_PROVIDER,
        "live_billing_enabled": LIVE_BILLING_ENABLED,
        "upgrade_path": "manual_non_production_only",
        "private_execution_access": False,
        "private_execution_feature_denylist": sorted(PRIVATE_EXECUTION_FEATURE_DENYLIST),
    }


def refuse_private_execution_entitlement(feature: str = "private_execution") -> None:
    """Explicit hard-ban helper for adversarial probes."""
    assert_not_private_execution_feature(feature)
