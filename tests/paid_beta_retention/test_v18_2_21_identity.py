"""V18.2.21 paid-beta identity + retention loop proof (test identity only)."""
from __future__ import annotations

from backend.nexus_paid_beta_retention.auth_census import auth_commercial_census
from backend.nexus_paid_beta_retention.constants import MARKER
from backend.nexus_paid_beta_retention.service import ingest_alert, since_last_visit
from backend.nexus_paid_beta_retention.watchlist_store import get_watchlist_store
from backend.nexus_product_analytics.events import PRODUCT_EVENT_NAMES, get_analytics_store
from backend.nexus_public_auth.passwords import hash_password, verify_password
from backend.nexus_public_auth.service import PublicAuthMembershipService
from backend.nexus_public_auth.store import PublicAuthStore
from backend.nexus_public_auth.tokens import AuthTokenStore


def test_marker():
    assert MARKER == "PUBLIC_V18_2_22_CLOSED_BETA_READINESS_HEAD"


def test_password_hash_not_plaintext():
    h = hash_password("correct-horse-battery")
    assert "correct-horse-battery" not in h
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("correct-horse-battery", h) is True
    assert verify_password("wrong-password-xx", h) is False


def test_auth_census_ready():
    census = auth_commercial_census()
    assert census["census"]["signup"] == "READY"
    assert census["census"]["login"] == "READY"
    assert census["census"]["logout"] == "READY"
    assert census["census"]["email_verify"] == "READY"
    assert census["census"]["forgot_password"] == "READY"
    assert census["census"]["reset_password"] == "READY"
    assert census["census"]["session"] == "READY"
    assert census["paid_beta_identity_minimum_met"] is True
    assert census["census"]["production_billing"] is False


def test_retention_loop_signup_to_since_last_visit():
    """SIGNUP→LOGIN→DISCOVER→WATCHLIST→ALERT→NOTIFY→RETURN→SINCE LAST VISIT→EXPLAIN."""
    store = PublicAuthStore()
    tokens = AuthTokenStore()
    svc = PublicAuthMembershipService(store=store, tokens=tokens)

    # SIGNUP
    reg = svc.register_member(
        "beta_loop@example.com",
        "Beta Loop",
        password="TestPass123!",
    )
    assert reg["password_set"] is True
    assert reg["verification"]["token"]
    account_id = reg["account_id"]

    # EMAIL VERIFY
    verified = svc.verify_email(reg["verification"]["token"])
    assert verified["email_verified"] is True

    # LOGIN
    logged = svc.login_with_password("beta_loop@example.com", "TestPass123!")
    token = logged["session"]["token"]
    assert token
    auth = svc.authenticate_rate_limited(token)
    assert auth["account_id"] == account_id

    # DISCOVER / WATCHLIST ADD (server canonical)
    wl = get_watchlist_store().add(account_id, "BTCUSDT")
    assert wl["authority"] == "SERVER"
    assert any(i["symbol"] == "BTCUSDT" for i in wl["items"])

    # ALERT EVENT → NOTIFICATION CENTER
    alert = ingest_alert(
        account_id,
        event_type="RADAR_UP",
        symbol="BTCUSDT",
        severity="HIGH",
        headline="BTC radar up (test)",
        metric={"dedup": "loop-1"},
    )
    assert alert["ok"] is True
    assert alert["notification"]["read"] is False

    # First visit → honest empty / insufficient history
    first = since_last_visit(account_id)
    assert first["insufficient_history"] is True
    assert first["fabricated"] is False
    assert first["notifications_since"] == []

    # RETURN → SINCE LAST VISIT with real history
    second = since_last_visit(account_id)
    assert second["has_previous"] is True
    assert second["insufficient_history"] is False
    assert second["fabricated"] is False
    assert "explain" in second

    # LOGOUT invalidates session
    out = svc.logout(token)
    assert out["revoked"] is True
    try:
        svc.authenticate_rate_limited(token)
        raise AssertionError("revoked session must fail")
    except Exception:
        pass

    # FORGOT + RESET (one-time)
    forgot = svc.forgot_password("beta_loop@example.com")
    assert forgot["reset"]["token"]
    reset = svc.reset_password(forgot["reset"]["token"], "NewPass456!")
    assert reset["one_time_token_consumed"] is True
    try:
        svc.reset_password(forgot["reset"]["token"], "AnotherPass789!")
        raise AssertionError("reset token must be one-time")
    except Exception:
        pass
    again = svc.login_with_password("beta_loop@example.com", "NewPass456!")
    assert again["session"]["token"]


def test_product_analytics_contract():
    store = get_analytics_store()
    assert "signup_completed" in PRODUCT_EVENT_NAMES
    assert "returned_from_alert" in PRODUCT_EVENT_NAMES
    r = store.record("radar_opened", account_id="acct_x", props={"password": "leak", "symbol": "ETHUSDT"})
    assert r["ok"] is True
    assert "password" not in r["event"]["props"]
    assert r["event"]["props"].get("symbol") == "ETHUSDT"
