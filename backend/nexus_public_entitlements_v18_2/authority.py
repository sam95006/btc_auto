"""Server-side entitlement authority (single source for public plans)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_public_entitlements_v18_2.capability_registry import PUBLIC_CAPABILITY_REGISTRY
from backend.nexus_public_entitlements_v18_2.constants import (
    BRAND_CONFIG,
    FORBIDDEN_CAPABILITY_IDS,
    LEGACY_TIER_TO_PLAN,
    MEMBERSHIP_PLANS,
    POLICY_VERSION,
)
from backend.nexus_public_entitlements_v18_2.errors import EntitlementDenial
from backend.nexus_public_entitlements_v18_2.org_roles import org_role_has_capability
from backend.nexus_public_entitlements_v18_2.policy_matrix import PLAN_CAPABILITIES, PLAN_LIMITS


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_plan(raw: str | None) -> str:
    if not raw:
        return "VISITOR"
    key = raw.strip()
    if key in MEMBERSHIP_PLANS:
        return key
    mapped = LEGACY_TIER_TO_PLAN.get(key) or LEGACY_TIER_TO_PLAN.get(key.lower())
    if mapped:
        return mapped
    return "VISITOR"


def minimum_plan_for_capability(capability_id: str) -> str | None:
    PUBLIC_CAPABILITY_REGISTRY.assert_read_only(capability_id)
    for plan in MEMBERSHIP_PLANS:
        if capability_id in PLAN_CAPABILITIES[plan]:
            return plan
    return None


class PublicEntitlementAuthority:
    """Canonical server entitlement resolver."""

    authority_id = "PUBLIC_ENTITLEMENT_AUTHORITY_V18_2"

    def has_capability(
        self,
        plan: str,
        capability_id: str,
        *,
        org_role: str | None = None,
    ) -> bool:
        normalized = normalize_plan(plan)
        PUBLIC_CAPABILITY_REGISTRY.assert_read_only(capability_id)
        if capability_id in PLAN_CAPABILITIES.get(normalized, frozenset()):
            return True
        if normalized == "ENTERPRISE" and org_role:
            return org_role_has_capability(org_role, capability_id)
        return False

    def require_capability(
        self,
        plan: str,
        capability_id: str,
        *,
        org_role: str | None = None,
    ) -> None:
        if capability_id in FORBIDDEN_CAPABILITY_IDS:
            denial = EntitlementDenial(
                code="POLICY_DENIED",
                capability_id=capability_id,
                current_plan=normalize_plan(plan),
                required_plan=None,
                message=f"Forbidden capability {capability_id}",
                upgrade_display="Contact Sales",
            )
            body, status = denial.to_response()
            raise EntitlementRequiredError(body, status)
        try:
            PUBLIC_CAPABILITY_REGISTRY.assert_read_only(capability_id)
        except (KeyError, ValueError) as exc:
            denial = EntitlementDenial(
                code="POLICY_DENIED",
                capability_id=capability_id,
                current_plan=normalize_plan(plan),
                required_plan=None,
                message=str(exc),
                upgrade_display="PRICE_TBD",
            )
            body, status = denial.to_response()
            raise EntitlementRequiredError(body, status) from exc
        if self.has_capability(plan, capability_id, org_role=org_role):
            return
        normalized = normalize_plan(plan)
        required = minimum_plan_for_capability(capability_id)
        upgrade = "Contact Sales" if required == "ENTERPRISE" else "PRICE_TBD"
        denial = EntitlementDenial(
            code="ENTITLEMENT_REQUIRED",
            capability_id=capability_id,
            current_plan=normalized,
            required_plan=required,
            message=f"Capability {capability_id} not granted for plan {normalized}",
            upgrade_display=upgrade,
        )
        body, status = denial.to_response()
        raise EntitlementRequiredError(body, status)

    def build_dto(
        self,
        *,
        plan: str,
        entitlement_source: str = "policy_default",
        org_role: str | None = None,
        effective_at: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_plan(plan)
        caps = sorted(PLAN_CAPABILITIES.get(normalized, frozenset()))
        return {
            "schema": "public_entitlement_dto_v18_2",
            "authority_id": self.authority_id,
            "policy_version": POLICY_VERSION,
            "plan": normalized,
            "legacy_tier_mapping_applied": normalized != (plan or "").strip(),
            "entitlement_source": entitlement_source,
            "capabilities": caps,
            "limits": PLAN_LIMITS.get(normalized, {}),
            "org_role": org_role,
            "effective_at": effective_at or _utc_now(),
            "expires_at": expires_at,
            "brand": dict(BRAND_CONFIG),
            "production_billing": False,
            "read_only": True,
        }


class EntitlementRequiredError(Exception):
    def __init__(self, body: dict[str, Any], status: int) -> None:
        super().__init__(body.get("message", "entitlement required"))
        self.body = body
        self.status = status


# Singleton — acceptance: single_entitlement_authority_count = 1
PUBLIC_ENTITLEMENT_AUTHORITY = PublicEntitlementAuthority()
