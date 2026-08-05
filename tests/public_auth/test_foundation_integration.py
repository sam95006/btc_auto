"""PUB2-F + PUB2-H foundation integration tests (MFA + ACL hardening)."""
from __future__ import annotations

import pytest

from backend.nexus_public_auth import (
    HARD_BANS,
    PRIVATE_EXECUTION_FEATURE_DENYLIST,
    PUBLIC_IDENTITY_REALM,
    PUBLIC_JWT_ISSUER,
    HardBanViolation,
    PublicAuthMembershipService,
)
from backend.nexus_public_auth.rate_limit import AuthRateLimiter, reset_default_rate_limiter
from backend.nexus_public_auth.store import PublicAuthStore, reset_default_store


@pytest.fixture()
def svc():
    reset_default_store()
    reset_default_rate_limiter()
    store = PublicAuthStore()
    return PublicAuthMembershipService(
        store=store,
        rate_limiter=AuthRateLimiter(
            limits={
                "register": 100,
                "session_create": 100,
                "tier_assign": 100,
                "session_authenticate": 100,
                "export": 100,
                "delete": 100,
                "consent": 100,
                "mfa_challenge": 100,
            }
        ),
    )


def test_foundation_status_reports_isolated_realm(svc: PublicAuthMembershipService):
    status = svc.foundation_status()
    assert status["public_identity_realm"] == PUBLIC_IDENTITY_REALM
    assert status["public_jwt_issuer"] == PUBLIC_JWT_ISSUER
    assert status["shared_jwt_issuer_count"] == 0
    assert status["live_billing_enabled"] is False
    assert status["production_customer_database"] is False
    assert status["private_execution_access_via_entitlement"] is False
    assert status["mfa_ready"] is True
    assert "no_live_billing" in HARD_BANS
    assert "no_shared_private_jwt_issuer" in HARD_BANS
    assert "no_private_admin_session_reuse" in HARD_BANS
    assert "private_execution" in PRIVATE_EXECUTION_FEATURE_DENYLIST


def test_register_roles_entitlements_session_consent_export_delete(svc: PublicAuthMembershipService):
    reg = svc.register_member("member@example.com", "Member One", tier="Free")
    account_id = reg["account_id"]

    org = svc.create_org(owner_account_id=account_id, name="Demo Org")
    svc.assign_org_roles(
        account_id,
        org["org_id"],
        ["org_owner", "org_member"],
        actor_account_id=account_id,
    )
    svc.assign_team_roles(
        account_id,
        "team_demo",
        ["team_member"],
        actor_account_id=account_id,
        org_id=org["org_id"],
    )
    svc.set_tier_manual(account_id, "Pro", actor="manual:operator_stub")
    assert svc.check_feature(account_id, "decision_detail_full") is True
    with pytest.raises(HardBanViolation):
        svc.require_account_feature(account_id, "org_audit_export")
    with pytest.raises(HardBanViolation):
        svc.check_feature(account_id, "private_execution")

    svc.consent.set_consent(account_id, "terms_of_service", granted=True)
    svc.consent.set_consent(account_id, "privacy_policy", granted=True)
    consent = svc.consent.get_consent(account_id)
    assert consent["terms_of_service"]["granted"] is True
    assert consent["marketing_email"]["granted"] is False

    session = svc.create_session_rate_limited(
        account_id, tier="Pro", member_roles=["member"]
    )
    auth = svc.authenticate_rate_limited(session["token"])
    assert auth["account_id"] == account_id
    assert auth["realm"] == PUBLIC_IDENTITY_REALM
    assert auth["issuer"] == PUBLIC_JWT_ISSUER

    svc.sessions.revoke_session(session["session_id"], reason="test_revoke")
    with pytest.raises(HardBanViolation):
        svc.sessions.authenticate(session["token"])

    enrolled = svc.mfa.enroll_factor(account_id, "totp", label="primary")
    confirmed = svc.mfa.confirm_enrollment(
        account_id,
        enrolled["factor_id"],
        enrollment_secret=enrolled["enrollment_secret_once"],
    )
    assert confirmed["status"] == "enabled"
    stored = svc.store.get_mfa_factor(enrolled["factor_id"])
    assert stored is not None
    assert "enrollment_secret_once" not in (stored.metadata or {})

    with pytest.raises(HardBanViolation):
        svc.create_session_rate_limited(
            account_id, tier="Pro", member_roles=["member"]
        )

    challenge = svc.mfa.create_challenge(account_id, enrolled["factor_id"])
    verified = svc.mfa.verify_challenge(
        account_id,
        challenge["challenge_id"],
        response_code=challenge["stub_response_hint"],
    )
    assert verified["verified"] is True
    assert svc.mfa.mfa_status(account_id)["enabled_factor_count"] == 1

    session2 = svc.create_session_rate_limited(
        account_id,
        tier="Pro",
        member_roles=["member"],
        mfa_challenge_id=challenge["challenge_id"],
    )
    assert session2["mfa_verified"] is True
    assert session2["private_execution_access"] is False
    export = svc.lifecycle.export_account_data(account_id)
    assert export["schema"] == "public_account_export_v2"
    assert export["account"]["email"] == "member@example.com"
    assert any("No private Lesson Memory" in n for n in export["notes"])
    assert any("No private execution access" in n for n in export["notes"])
    assert len(export["mfa_factors"]) == 1
    assert export["actor_account_id"] == account_id

    pending = svc.lifecycle.request_deletion(account_id)
    assert pending["status"] == "deletion_pending"
    with pytest.raises(HardBanViolation):
        svc.sessions.authenticate(session2["token"])

    final = svc.lifecycle.finalize_deletion(account_id)
    assert final["status"] == "deleted"
    account = svc.store.get_account(account_id)
    assert account is not None
    assert account.email.startswith("deleted+")
    assert account.display_name == "DELETED"

    events = svc.store.list_audit(account_id=account_id)
    actions = {e["action"] for e in events}
    assert "account.register" in actions
    assert "session.revoke" in actions
    assert "account.data_export" in actions
    assert "account.deleted" in actions
    assert "consent.update" in actions
    assert "mfa.enroll_confirmed" in actions


def test_enterprise_entitlement_matrix(svc: PublicAuthMembershipService):
    reg = svc.register_member("ent@example.com", "Ent", tier="Free")
    svc.set_tier_manual(reg["account_id"], "Enterprise", actor="manual:qa")
    snap = svc.entitlements(reg["account_id"])
    assert "org_roles" in snap["features"]
    assert snap["live_billing_enabled"] is False
    assert snap["billing_provider"] == "NONE_NON_PRODUCTION"
    assert snap["private_execution_access"] is False
    assert "private_execution" not in snap["features"]


def test_stripe_actor_blocked(svc: PublicAuthMembershipService):
    reg = svc.register_member("x@example.com", "X", tier="Free")
    with pytest.raises(HardBanViolation):
        svc.set_tier_manual(reg["account_id"], "Pro", actor="stripe:cus_123")


def test_unsigned_org_assign_blocked(svc: PublicAuthMembershipService):
    reg = svc.register_member("u@example.com", "U")
    with pytest.raises(HardBanViolation):
        svc.assign_org_roles(reg["account_id"], "org_x", ["org_owner"])


def test_self_register_cannot_escalate_tier(svc: PublicAuthMembershipService):
    with pytest.raises(HardBanViolation):
        svc.register_member("bad@example.com", "Bad", tier="Enterprise")
