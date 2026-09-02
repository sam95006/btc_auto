"""NEXUS-EXPERIENCE-1B.1.1 — Trial-truth: the Starter trial starts from the real
ACCOUNT registration timestamp (nexus.accounts.created_at, exposed by the session
identity), NOT from Subscription.created_at, the billing row, now(), or any
browser-supplied value.

These tests deliberately give the subscription row a DIFFERENT created_at from the
account registration time so a future regression back to Subscription.created_at
would fail here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Flask

from backend.nexus_billing.routes import SUBSCRIPTION_REPO_CONFIG_KEY, register_billing_routes
from backend.nexus_billing.subscription import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    Subscription,
    default_subscription,
)
from backend.nexus_personal.routes import register_personal_routes

H = {"X-Nexus-Session": "sid"}


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat()


class _FakeAuth:
    """Session identity mirrors get_active_session: it carries the ACCOUNT
    registration timestamp (`created_at`)."""

    def __init__(self, account_created_iso):
        self._created = account_created_iso

    def resolve_session(self, sid):
        if sid != "sid":
            return None
        return {"account_id": "acct", "email": "u@nexus.local", "status": "ACTIVE",
                "created_at": self._created}


class _SubRepo:
    def __init__(self, sub):
        self._sub = sub

    def get_by_account(self, aid):
        return self._sub if aid == "acct" else None


def _client(account_created_iso, sub):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": _FakeAuth(account_created_iso)}
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = _SubRepo(sub)
    register_billing_routes(app)
    register_personal_routes(app)
    return app.test_client()


def test_requires_auth():
    assert _client(None, default_subscription("acct")).get("/api/v1/personal/subscription").status_code == 401


def test_trial_uses_account_registration_not_subscription_created_at():
    # Account registered 3 days ago -> active trial, ~27 days left.
    account_reg = _iso(_now() - timedelta(days=3))
    # Subscription row created 60 days ago: if this were (wrongly) used as the trial
    # start, the trial would read EXPIRED. It must be IGNORED.
    sub = Subscription(account_id="acct", plan_code="free", status=STATUS_INACTIVE,
                       created_at=_now() - timedelta(days=60))
    d = _client(account_reg, sub).get("/api/v1/personal/subscription", headers=H).get_json()
    assert d["trial"]["state"] == "TRIAL"
    assert d["trial"]["trial_active"] is True
    assert d["trial"]["days_remaining"] >= 25          # ~27 of 30
    assert d["effective_plan"] == "starter"             # active trial grants Starter
    assert d["trial_contract"]["auto_charge"] is False


def test_expired_by_account_age_even_if_subscription_row_is_recent():
    # Account registered 45 days ago -> trial expired, even though the subscription
    # row was created 1 day ago (which must NOT reset the trial).
    account_reg = _iso(_now() - timedelta(days=45))
    sub = Subscription(account_id="acct", plan_code="free", status=STATUS_INACTIVE,
                       created_at=_now() - timedelta(days=1))
    d = _client(account_reg, sub).get("/api/v1/personal/subscription", headers=H).get_json()
    assert d["trial"]["state"] == "TRIAL_EXPIRED"
    assert d["trial"]["trial_active"] is False
    assert d["effective_plan"] == "free"


def test_paid_plan_wins_over_trial():
    account_reg = _iso(_now() - timedelta(days=3))       # would otherwise be an active trial
    sub = Subscription(account_id="acct", plan_code="pro", status=STATUS_ACTIVE,
                       created_at=_now() - timedelta(days=3))
    d = _client(account_reg, sub).get("/api/v1/personal/subscription", headers=H).get_json()
    assert d["effective_plan"] == "pro"
    assert d["trial"]["trial_active"] is False


def test_unavailable_when_account_registration_missing():
    # Identity has no account created_at -> cannot compute a real trial window.
    d = _client(None, default_subscription("acct")).get("/api/v1/personal/subscription", headers=H).get_json()
    assert d["trial"]["state"] == "UNAVAILABLE"
    assert "days_remaining" not in d["trial"]
    assert "trial_ends_at" not in d["trial"]
    assert d["trial_contract"]["auto_charge"] is False   # generic offer still safe


def test_browser_cannot_override_registered_at():
    # Account registered 45 days ago (expired). A browser attempt to inject a fresh
    # registered_at via query/body must be ignored — identity is server-derived.
    account_reg = _iso(_now() - timedelta(days=45))
    c = _client(account_reg, default_subscription("acct"))
    fresh = _iso(_now())
    d = c.get(f"/api/v1/personal/subscription?registered_at={fresh}",
              json={"registered_at": fresh, "account_id": "someone_else"}, headers=H).get_json()
    assert d["trial"]["state"] == "TRIAL_EXPIRED"        # server account time wins
    assert d["trial"]["trial_active"] is False
