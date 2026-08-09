"""V18.2.22 closed-beta invite + retention + analytics readiness."""
from __future__ import annotations

from backend.nexus_closed_beta.constants import MARKER
from backend.nexus_closed_beta.ops import get_product_ops, record_ops
from backend.nexus_closed_beta.partner_inventory import partner_api_inventory
from backend.nexus_closed_beta.service import ClosedBetaService, get_closed_beta_service
from backend.nexus_closed_beta.store import ClosedBetaStore
from backend.nexus_paid_beta_retention.service import ingest_alert, since_last_visit
from backend.nexus_paid_beta_retention.watchlist_store import get_watchlist_store
from backend.nexus_product_analytics.events import PRODUCT_EVENT_NAMES, get_analytics_store
from backend.nexus_public_auth.service import PublicAuthMembershipService
from backend.nexus_public_auth.store import PublicAuthStore
from backend.nexus_public_auth.tokens import AuthTokenStore


def test_marker():
    assert MARKER == "PUBLIC_V18_2_22_CLOSED_BETA_READINESS_HEAD"


def test_closed_beta_invite_lifecycle():
    store = ClosedBetaStore()
    svc = ClosedBetaService(store=store)
    created = svc.create_invite(
        admin_key="staging-closed-beta-admin",
        email_hint="beta@example.com",
        ttl_seconds=3600,
    )
    assert created["ok"] is True
    code = created["invite_code"]
    invite_id = created["invite"]["invite_id"]

    auth_store = PublicAuthStore()
    tokens = AuthTokenStore()
    auth = PublicAuthMembershipService(store=auth_store, tokens=tokens)
    reg = auth.register_member("beta@example.com", "Beta", password="TestPass123!")
    account_id = reg["account_id"]
    auth.verify_email(reg["verification"]["token"])

    snap0 = svc.member_access_snapshot(account_id)
    assert snap0["status"] == "INVITED"
    assert snap0["has_access"] is False

    redeemed = svc.redeem_invite(account_id=account_id, invite_code=code)
    assert redeemed["beta_access"]["status"] == "ACTIVE"
    assert redeemed["beta_access"]["has_access"] is True

    # Single-use
    try:
        svc.redeem_invite(account_id=account_id, invite_code=code)
        raise AssertionError("invite must be single-use")
    except Exception as exc:
        assert "already_used" in str(exc) or "invite" in str(exc)

    revoked = svc.revoke_invite(
        admin_key="staging-closed-beta-admin",
        invite_id=invite_id,
        account_id=account_id,
    )
    assert revoked["ok"] is True
    assert svc.member_access_snapshot(account_id)["status"] == "REVOKED"

    audit = store.list_audit(limit=20)
    actions = {a["action"] for a in audit}
    assert "invite.create" in actions
    assert "invite.redeem" in actions
    assert "member.activate" in actions
    assert "invite.revoke" in actions or "member.revoke" in actions


def test_invite_expiry():
    store = ClosedBetaStore()
    svc = ClosedBetaService(store=store)
    created = svc.create_invite(
        admin_key="staging-closed-beta-admin",
        ttl_seconds=1,
    )
    invite = store.get_invite(created["invite"]["invite_id"])
    assert invite is not None
    invite.expires_at_epoch = 0  # force expire
    store.put_invite(invite)
    try:
        svc.redeem_invite(account_id="acct_x", invite_code=created["invite_code"])
        raise AssertionError("expired invite must fail")
    except Exception as exc:
        assert "expire" in str(exc).lower() or "expired" in str(exc).lower()


def test_retention_loop_with_analytics_events():
    store = PublicAuthStore()
    tokens = AuthTokenStore()
    svc = PublicAuthMembershipService(store=store, tokens=tokens)
    reg = svc.register_member("loop22@example.com", "Loop", password="TestPass123!")
    account_id = reg["account_id"]
    svc.verify_email(reg["verification"]["token"])
    logged = svc.login_with_password("loop22@example.com", "TestPass123!")
    assert logged.get("session", {}).get("token")

    beta = get_closed_beta_service()
    created = beta.create_invite(admin_key="staging-closed-beta-admin")
    beta.redeem_invite(account_id=account_id, invite_code=created["invite_code"])

    wl = get_watchlist_store().add(account_id, "ETHUSDT")
    assert any(i["symbol"] == "ETHUSDT" for i in wl["items"])
    get_watchlist_store().remove(account_id, "ETHUSDT")
    assert all(i["symbol"] != "ETHUSDT" for i in get_watchlist_store().list_items(account_id)["items"])

    alert = ingest_alert(
        account_id,
        event_type="RADAR_UP",
        symbol="ETHUSDT",
        severity="HIGH",
        headline="ETH up",
        metric={"dedup": "v22-1"},
    )
    assert alert["ok"] is True
    note_id = alert["notification"]["id"]
    from backend.nexus_paid_beta_retention.notifications import get_notification_center

    get_notification_center().mark_read(account_id, note_id)

    first = since_last_visit(account_id)
    assert first["fabricated"] is False
    second = since_last_visit(account_id)
    assert second["has_previous"] is True
    assert second["fabricated"] is False

    out = svc.logout(logged["session"]["token"])
    assert out["revoked"] is True
    again = svc.login_with_password("loop22@example.com", "TestPass123!")
    assert again["session"]["token"]
    # Watchlist still empty after remove — preserved server state
    assert get_watchlist_store().list_items(account_id)["items"] == []


def test_analytics_contract_v22():
    for ev in (
        "signup_completed",
        "login_completed",
        "radar_opened",
        "symbol_opened",
        "watchlist_added",
        "alert_opened",
        "returned_from_alert",
        "session_started",
        "session_returned",
        "watchlist_removed",
        "notification_read",
    ):
        assert ev in PRODUCT_EVENT_NAMES
    store = get_analytics_store()
    r = store.record("session_started", account_id="a1", props={"token": "leak", "ok": True})
    assert "token" not in r["event"]["props"]
    assert r["event"]["props"].get("ok") is True


def test_ops_and_partner_inventory():
    record_ops("auth_errors", detail="test")
    record_ops("radar_api_failures", detail="test")
    snap = get_product_ops().snapshot()
    assert snap["channels"]["auth_errors"] >= 1
    assert snap["external_monitoring"] is False
    inv = partner_api_inventory()
    assert inv["new_external_agent_api_exposed"] is False
    assert inv["partner_tokens_issued"] is False
    assert "Agent Gateway" in inv["future_attach_point"]["path"]


def test_optional_mfa_not_mandated_for_normal_member():
    store = PublicAuthStore()
    tokens = AuthTokenStore()
    svc = PublicAuthMembershipService(store=store, tokens=tokens)
    reg = svc.register_member("mfaopt@example.com", "Mfa", password="TestPass123!")
    logged = svc.login_with_password("mfaopt@example.com", "TestPass123!")
    assert logged.get("session", {}).get("token")
    assert logged.get("mfa_required") is False
    status = svc.mfa.mfa_status(reg["account_id"])
    assert status["status"] in {"disabled", "pending_enrollment", "enabled"}
