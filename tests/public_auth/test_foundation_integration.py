"""PUB-H foundation integration tests."""
from __future__ import annotations

import pytest

from backend.nexus_public_auth import (
    HARD_BANS,
    PUBLIC_IDENTITY_REALM,
    PUBLIC_JWT_ISSUER,
    HardBanViolation,
    PublicAuthMembershipService,
)
from backend.nexus_public_auth.store import PublicAuthStore, reset_default_store


@pytest.fixture()
def svc():
    reset_default_store()
    store = PublicAuthStore()
    return PublicAuthMembershipService(store=store)


def test_foundation_status_reports_isolated_realm(svc: PublicAuthMembershipService):
    status = svc.foundation_status()
    assert status["public_identity_realm"] == PUBLIC_IDENTITY_REALM
    assert status["public_jwt_issuer"] == PUBLIC_JWT_ISSUER
    assert status["shared_jwt_issuer_count"] == 0
    assert status["live_billing_enabled"] is False
    assert status["production_customer_database"] is False
    assert "no_live_billing" in HARD_BANS
    assert "no_shared_private_jwt_issuer" in HARD_BANS
    assert "no_private_admin_session_reuse" in HARD_BANS


def test_register_roles_entitlements_session_consent_export_delete(svc: PublicAuthMembershipService):
    reg = svc.register_member("member@example.com", "Member One", tier="Free")
    account_id = reg["account_id"]

    svc.assign_org_roles(account_id, "org_demo", ["org_member"])
    svc.assign_team_roles(account_id, "team_demo", ["team_member"])
    svc.set_tier_manual(account_id, "Pro", actor="manual:operator_stub")
    assert svc.check_feature(account_id, "decision_detail_full") is True
    with pytest.raises(HardBanViolation):
        svc.require_account_feature(account_id, "org_audit_export")

    svc.consent.set_consent(account_id, "terms_of_service", granted=True)
    svc.consent.set_consent(account_id, "privacy_policy", granted=True)
    consent = svc.consent.get_consent(account_id)
    assert consent["terms_of_service"]["granted"] is True
    assert consent["marketing_email"]["granted"] is False

    session = svc.sessions.create_session(
        account_id, tier="Pro", member_roles=["member"]
    )
    auth = svc.sessions.authenticate(session["token"])
    assert auth["account_id"] == account_id
    assert auth["realm"] == PUBLIC_IDENTITY_REALM
    assert auth["issuer"] == PUBLIC_JWT_ISSUER

    svc.sessions.revoke_session(session["session_id"], reason="test_revoke")
    with pytest.raises(HardBanViolation):
        svc.sessions.authenticate(session["token"])

    # New session for export/delete path
    session2 = svc.sessions.create_session(
        account_id, tier="Pro", member_roles=["member"]
    )
    export = svc.lifecycle.export_account_data(account_id)
    assert export["schema"] == "public_account_export_v1"
    assert export["account"]["email"] == "member@example.com"
    assert any("No private Lesson Memory" in n for n in export["notes"])

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


def test_enterprise_entitlement_matrix(svc: PublicAuthMembershipService):
    reg = svc.register_member("ent@example.com", "Ent", tier="Enterprise")
    snap = svc.entitlements(reg["account_id"])
    assert "org_roles" in snap["features"]
    assert snap["live_billing_enabled"] is False
    assert snap["billing_provider"] == "NONE_NON_PRODUCTION"


def test_stripe_actor_blocked(svc: PublicAuthMembershipService):
    reg = svc.register_member("x@example.com", "X", tier="Free")
    with pytest.raises(HardBanViolation):
        svc.set_tier_manual(reg["account_id"], "Pro", actor="stripe:cus_123")
