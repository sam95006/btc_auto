"""Unit coverage for identity, roles, entitlements, sessions."""
from __future__ import annotations

import pytest

from backend.nexus_public_auth.entitlements import (
    assign_tier_manual,
    features_for_tier,
    has_feature,
)
from backend.nexus_public_auth.hard_bans import HardBanViolation
from backend.nexus_public_auth.jwt_issuer import PublicJwtIssuer
from backend.nexus_public_auth.roles import (
    normalize_member_roles,
    normalize_org_roles,
    normalize_team_roles,
)
from backend.nexus_public_auth.service import PublicAuthMembershipService
from backend.nexus_public_auth.store import PublicAuthStore


def test_tier_feature_ladder():
    assert has_feature("Free", "decision_feed_read")
    assert not has_feature("Free", "decision_detail_full")
    assert has_feature("Pro", "decision_detail_full")
    assert has_feature("Elite", "nex_ai_conversation")
    assert "org_audit_export" in features_for_tier("Enterprise")


def test_manual_tier_assignment_metadata():
    change = assign_tier_manual(
        current_tier="Free", target_tier="Elite", actor="manual:qa"
    )
    assert change["assignment_mode"] == "manual_non_production"
    assert change["live_billing_enabled"] is False


def test_role_normalization():
    assert normalize_member_roles(["member", "member_admin"]) == [
        "member",
        "member_admin",
    ]
    assert normalize_org_roles(["org_owner"]) == ["org_owner"]
    assert normalize_team_roles(["team_lead", "team_reviewer"]) == [
        "team_lead",
        "team_reviewer",
    ]
    with pytest.raises(HardBanViolation):
        normalize_org_roles(["private_operator"])


def test_jwt_roundtrip_and_expiry_realm():
    issuer = PublicJwtIssuer(secret="unit-test-public-secret")
    issued = issuer.issue(
        account_id="acct_1",
        tier="Pro",
        member_roles=["member"],
        ttl_seconds=60,
    )
    payload = issuer.verify(issued["token"])
    assert payload["sub"] == "acct_1"
    assert payload["tier"] == "Pro"
    assert payload["realm"].startswith("nexus.public")


def test_revoke_all_sessions():
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(store=store)
    reg = svc.register_member("a@example.com", "A")
    s1 = svc.sessions.create_session(
        reg["account_id"], tier="Free", member_roles=["member"]
    )
    s2 = svc.sessions.create_session(
        reg["account_id"], tier="Free", member_roles=["member"]
    )
    n = svc.sessions.revoke_all_for_account(reg["account_id"])
    assert n == 2
    for token in (s1["token"], s2["token"]):
        with pytest.raises(HardBanViolation):
            svc.sessions.authenticate(token)
