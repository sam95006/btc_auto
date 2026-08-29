"""Central entitlement / feature-access engine for BILLING-2.

Resolves what an account may use strictly from the backend:

    Account -> Subscription -> Plan -> Plan Entitlements -> Feature Access

This is the entitlement dimension only. It is intentionally SEPARATE from RBAC
(role-based authority): a final feature gate may require both RBAC PASS AND
ENTITLEMENT PASS, but the two are distinct data sets and are never merged here.

Fail-safe: any missing/ambiguous/non-live/invalid case resolves to the free
tier. A paid entitlement is granted only for a legitimately live subscription.

Trading firewall: entitlements NEVER include or imply trading-execution
authorization. Membership tier is not trading authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Union

from backend.nexus_billing.features import ALL_FEATURES, FEATURE_GROUPS, is_valid_feature
from backend.nexus_billing.plans import DEFAULT_PLAN_CODE, get_plan
from backend.nexus_billing.subscription import (
    LIVE_STATUSES,
    STATUS_INACTIVE,
    Subscription,
)

# Cumulative capability tiers: each tier includes everything below it.
PLAN_TIER_ORDER: tuple[str, ...] = ("free", "starter", "pro", "advanced", "enterprise")

# An entitlement value is a capability flag (True) or, for future limit-style
# entitlements, a numeric quota. The engine is intentionally not boolean-only.
EntitlementValue = Union[bool, int]


def _cumulative_entitlements(plan_code: str) -> dict[str, EntitlementValue]:
    """Accumulate feature groups up to and including the plan's tier."""
    entitlements: dict[str, EntitlementValue] = {}
    if plan_code not in PLAN_TIER_ORDER:
        plan_code = DEFAULT_PLAN_CODE
    tier_index = PLAN_TIER_ORDER.index(plan_code)
    for tier in PLAN_TIER_ORDER[: tier_index + 1]:
        for feature_code in FEATURE_GROUPS[tier]:
            # Capability flag by default. Limit-style values can be layered in
            # later without changing this shape.
            entitlements[feature_code] = True
    return entitlements


# Precomputed, deterministic plan -> entitlement mapping (code-level config).
PLAN_ENTITLEMENTS: dict[str, dict[str, EntitlementValue]] = {
    plan: _cumulative_entitlements(plan) for plan in PLAN_TIER_ORDER
}


def effective_plan_code(subscription: Optional[Subscription]) -> str:
    """The plan whose entitlements actually apply. Only a live subscription on a
    known plan yields a paid plan; everything else is free (fail-safe)."""
    if subscription is None:
        return DEFAULT_PLAN_CODE
    if subscription.status not in LIVE_STATUSES:
        return DEFAULT_PLAN_CODE
    plan = get_plan(subscription.plan_code)
    if plan is None or plan.code not in PLAN_TIER_ORDER:
        return DEFAULT_PLAN_CODE
    return plan.code


@dataclass(frozen=True)
class EntitlementResolution:
    effective_plan_code: str
    subscription_status: str
    entitlements: dict[str, EntitlementValue]

    @property
    def feature_codes(self) -> list[str]:
        # Deterministic order matching the catalog.
        return [code for code in ALL_FEATURES if self.entitlements.get(code)]

    def has(self, feature_code: Optional[str]) -> bool:
        if not is_valid_feature(feature_code):
            return False
        value = self.entitlements.get(feature_code)  # type: ignore[arg-type]
        if value is True:
            return True
        if isinstance(value, int) and not isinstance(value, bool):
            return value > 0
        return False

    def value(self, feature_code: Optional[str]) -> Optional[EntitlementValue]:
        if not is_valid_feature(feature_code):
            return None
        return self.entitlements.get(feature_code)  # type: ignore[arg-type]

    def to_public_dict(self) -> dict[str, Any]:
        # Member-facing: effective plan, status, and the entitled feature codes.
        # Never includes payment-provider internal identifiers.
        return {
            "effective_plan_code": self.effective_plan_code,
            "subscription_status": self.subscription_status,
            "entitlements": self.feature_codes,
        }


def resolve_entitlements(subscription: Optional[Subscription]) -> EntitlementResolution:
    """Resolve the effective entitlements for a (possibly absent) subscription.

    The subject here is a subscription rather than a raw user id, so a future
    organization-owned subscription can feed the same plan-based mapping without
    changing this engine.
    """
    status = subscription.status if subscription is not None else STATUS_INACTIVE
    plan_code = effective_plan_code(subscription)
    entitlements = dict(PLAN_ENTITLEMENTS.get(plan_code, PLAN_ENTITLEMENTS[DEFAULT_PLAN_CODE]))
    return EntitlementResolution(
        effective_plan_code=plan_code,
        subscription_status=status,
        entitlements=entitlements,
    )


def has_entitlement(subscription: Optional[Subscription], feature_code: str) -> bool:
    return resolve_entitlements(subscription).has(feature_code)


def plan_has_entitlement(plan_code: str, feature_code: str) -> bool:
    """Whether a plan (by code) includes a feature — used by usage metering to
    keep quota display/enforcement consistent with entitlements."""
    if not is_valid_feature(feature_code):
        return False
    entitlements = PLAN_ENTITLEMENTS.get(plan_code, PLAN_ENTITLEMENTS[DEFAULT_PLAN_CODE])
    value = entitlements.get(feature_code)
    return value is True or (isinstance(value, int) and not isinstance(value, bool) and value > 0)
