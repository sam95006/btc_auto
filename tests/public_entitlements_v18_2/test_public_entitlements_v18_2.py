"""Focused V18.2 public entitlements tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_entitlements_v18_2.authority import (
    PUBLIC_ENTITLEMENT_AUTHORITY,
    EntitlementRequiredError,
    normalize_plan,
)
from backend.nexus_public_entitlements_v18_2.capability_registry import (
    PUBLIC_CAPABILITY_REGISTRY,
    READ_ONLY_CAPABILITIES,
)
from backend.nexus_public_entitlements_v18_2.constants import (
    BILLING_STATUS,
    BRAND_STATUS,
    FORBIDDEN_CAPABILITY_IDS,
    PRICING_STATUS,
)
from backend.nexus_public_entitlements_v18_2.dto import navigation_contract_v18_2
from backend.nexus_public_entitlements_v18_2.hard_bans import count_registry_singletons, run_entitlement_scans
from backend.nexus_public_entitlements_v18_2.org_roles import ORG_ROLE_CAPABILITIES, org_role_has_capability
from backend.nexus_public_entitlements_v18_2.policy_matrix import PLAN_CAPABILITIES, PLAN_LIMITS


ROOT = Path(__file__).resolve().parents[2]


def test_single_capability_registry():
    caps = PUBLIC_CAPABILITY_REGISTRY.all_ids()
    assert len(caps) == len(READ_ONLY_CAPABILITIES)
    assert caps.isdisjoint(FORBIDDEN_CAPABILITY_IDS)
    singletons = count_registry_singletons(ROOT)
    assert singletons["single_capability_registry_count"] == 1


def test_single_entitlement_authority():
    singletons = count_registry_singletons(ROOT)
    assert singletons["single_entitlement_authority_count"] == 1
    dto = PUBLIC_ENTITLEMENT_AUTHORITY.build_dto(plan="FREE")
    assert dto["authority_id"] == PUBLIC_ENTITLEMENT_AUTHORITY.authority_id


def test_legacy_elite_maps_to_research():
    assert normalize_plan("Elite") == "RESEARCH"
    assert normalize_plan("ELITE_LEGACY") == "RESEARCH"
    assert "REGIME_PROBABILITY" in PLAN_CAPABILITIES["RESEARCH"]
    assert "REGIME_PROBABILITY" not in PLAN_CAPABILITIES["PRO"]


def test_plan_matrix_policy_limits_not_empty():
    for plan, limits in PLAN_LIMITS.items():
        assert plan in PLAN_CAPABILITIES
        assert "watchlist_max" in limits


def test_org_roles():
    assert org_role_has_capability("ORG_ADMIN", "AUDIT_LOG")
    assert not org_role_has_capability("VIEWER", "SSO")
    assert "ORG_ADMIN" in ORG_ROLE_CAPABILITIES


def test_403_entitlement_required():
    with pytest.raises(EntitlementRequiredError) as exc:
        PUBLIC_ENTITLEMENT_AUTHORITY.require_capability("FREE", "SCANNER_FULL")
    assert exc.value.body["error"] == "ENTITLEMENT_REQUIRED"
    assert exc.value.status == 403
    assert exc.value.body["upgrade_display"] == "PRICE_TBD"


def test_403_policy_denied_forbidden_cap():
    with pytest.raises(EntitlementRequiredError) as exc:
        PUBLIC_ENTITLEMENT_AUTHORITY.require_capability("PRO", "TRADE")
    assert exc.value.body["error"] == "POLICY_DENIED"


def test_public_dto_brand_pricing_freeze():
    dto = PUBLIC_ENTITLEMENT_AUTHORITY.build_dto(plan="VISITOR")
    assert dto["brand"]["brand_status"] == BRAND_STATUS
    assert dto["brand"]["pricing_status"] == PRICING_STATUS
    assert dto["production_billing"] is False
    assert dto["limits"] == PLAN_LIMITS["VISITOR"]


def test_navigation_contract_no_founder():
    nav = navigation_contract_v18_2()
    paths = [i["path"] for i in nav["primary_nav"]]
    assert "/founder/operator" not in paths
    assert len(nav["primary_nav"]) == 4


def test_acceptance_scans():
    scans = run_entitlement_scans(ROOT)
    reg = scans["registry_singletons"]
    assert reg["single_capability_registry_count"] == 1
    assert reg["single_entitlement_authority_count"] == 1
    assert scans["forbidden_registry"]["forbidden_capability_in_registry_count"] == 0
    assert scans["member_execution_control_count"] == 0
    assert scans["production_billing"] is False
    assert scans["brand_finalized"] is False
    assert scans["pricing_finalized"] is False
    assert BILLING_STATUS == "NOT_STARTED"
