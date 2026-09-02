"""NEXUS-EXPERIENCE-1B.1 — honest Starter-trial read model.

Guards the /api/v1/personal/subscription contract: real trial windows are computed
from the registration timestamp + paid plan, a paid subscription reports PAID, and
when the registration timestamp is unavailable the trial status is reported
UNAVAILABLE — never a fabricated countdown.
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


class _FakeAuth:
    def __init__(self) -> None:
        self.sessions = {"sid": "acct"}

    def resolve_session(self, sid):
        aid = self.sessions.get(sid)
        return {"account_id": aid} if aid else None


class _SubRepo:
    def __init__(self, sub) -> None:
        self._sub = sub

    def get_by_account(self, aid):
        return self._sub if aid == "acct" else None


def _app(sub):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": _FakeAuth()}
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = _SubRepo(sub)
    register_billing_routes(app)
    register_personal_routes(app)
    return app.test_client()


def test_requires_auth():
    # No session header -> honest 401, never an anonymous trial.
    c = _app(default_subscription("acct"))
    assert c.get("/api/v1/personal/subscription").status_code == 401


def test_active_trial_from_recent_registration():
    reg = datetime.now(timezone.utc) - timedelta(days=3)
    sub = Subscription(account_id="acct", plan_code="free", status=STATUS_INACTIVE, created_at=reg)
    d = _app(sub).get("/api/v1/personal/subscription", headers=H).get_json()
    assert d["trial"]["state"] == "TRIAL"
    assert d["trial"]["trial_active"] is True
    assert d["trial"]["days_remaining"] >= 25  # ~27 remaining of 30
    assert d["effective_plan"] == "starter"     # active trial grants Starter
    assert d["trial_contract"]["auto_charge"] is False
    assert d["trial_contract"]["days"] == 30


def test_expired_trial_falls_back_to_free():
    reg = datetime.now(timezone.utc) - timedelta(days=45)
    sub = Subscription(account_id="acct", plan_code="free", status=STATUS_INACTIVE, created_at=reg)
    d = _app(sub).get("/api/v1/personal/subscription", headers=H).get_json()
    assert d["trial"]["state"] == "TRIAL_EXPIRED"
    assert d["trial"]["trial_active"] is False
    assert d["effective_plan"] == "free"


def test_paid_plan_reports_paid_not_trial():
    reg = datetime.now(timezone.utc) - timedelta(days=100)
    sub = Subscription(account_id="acct", plan_code="pro", status=STATUS_ACTIVE, created_at=reg)
    d = _app(sub).get("/api/v1/personal/subscription", headers=H).get_json()
    assert d["effective_plan"] == "pro"
    assert d["trial"]["trial_active"] is False


def test_unavailable_when_registration_timestamp_missing():
    # default subscription has no created_at -> we cannot truthfully compute a trial
    # window, so the status is UNAVAILABLE (no invented countdown / end date).
    d = _app(default_subscription("acct")).get("/api/v1/personal/subscription", headers=H).get_json()
    assert d["trial"]["state"] == "UNAVAILABLE"
    assert "days_remaining" not in d["trial"]
    assert "trial_ends_at" not in d["trial"]
    # The generic offer is still truthful and safe to show.
    assert d["trial_contract"]["auto_charge"] is False
