from __future__ import annotations

from typing import Any, Optional

import pytest
from flask import Flask

from backend.nexus_billing.entitlements import resolve_entitlements
from backend.nexus_billing.event_repository import (
    DECISION_NEW,
    DECISION_RETRY,
    DECISION_TERMINAL_PROCESSED,
    DECISION_TERMINAL_REJECTED,
    STATUS_PROCESSED,
    STATUS_PROCESSING,
    STATUS_RECEIVED,
    STATUS_REJECTED,
    ProcessingClaim,
)
from backend.nexus_billing.mock_provider import MockPaymentProvider
from backend.nexus_billing.provider import EVENT_CHECKOUT_COMPLETED, ProviderEvent
from backend.nexus_billing.routes import (
    BILLING_SERVICE_CONFIG_KEY,
    MOCK_ENABLED_CONFIG_KEY,
    register_billing_routes,
)
from backend.nexus_billing.service import BillingError, BillingService
from backend.nexus_billing.subscription import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    Subscription,
    assert_transition,
)


class MemSubRepo:
    def __init__(self):
        self.by_account: dict[str, Subscription] = {}

    def get_by_account(self, aid):
        return self.by_account.get(aid)

    def create_subscription(self, *, account_id, plan_code, status=STATUS_INACTIVE, provider=None):
        s = Subscription(account_id=account_id, plan_code=plan_code, status=status, provider=provider)
        self.by_account[account_id] = s
        return s

    def ensure_subscription(self, aid):
        s = self.by_account.get(aid)
        if s is None:
            s = self.create_subscription(account_id=aid, plan_code="free", status=STATUS_INACTIVE)
        return s

    def apply_provider_transition(self, aid, to_status, *, plan_code=None, provider=None,
                                  provider_customer_id=None, provider_subscription_id=None, cancel_at_period_end=None):
        cur = self.ensure_subscription(aid)
        assert_transition(cur.status, to_status)
        cur.status = to_status
        if plan_code is not None:
            cur.plan_code = plan_code
        if provider is not None:
            cur.provider = provider
        if provider_customer_id is not None:
            cur.provider_customer_id = provider_customer_id
        if provider_subscription_id is not None:
            cur.provider_subscription_id = provider_subscription_id
        if cancel_at_period_end is not None:
            cur.cancel_at_period_end = bool(cancel_at_period_end)
        return cur

    def set_cancel_at_period_end(self, aid, value):
        self.ensure_subscription(aid).cancel_at_period_end = bool(value)


class MemEventRepo:
    def __init__(self):
        self.by_key = {}
        self.by_id = {}

    def begin_processing(self, event):
        key = (event.provider, event.provider_event_id)
        if key not in self.by_key:
            bid = f"be_{len(self.by_id) + 1}"
            self.by_key[key] = bid
            self.by_id[bid] = {"status": STATUS_PROCESSING}
            return ProcessingClaim(bid, DECISION_NEW)
        bid = self.by_key[key]
        st = self.by_id[bid]["status"]
        if st == STATUS_PROCESSED:
            return ProcessingClaim(bid, DECISION_TERMINAL_PROCESSED)
        if st == STATUS_REJECTED:
            return ProcessingClaim(bid, DECISION_TERMINAL_REJECTED)
        self.by_id[bid]["status"] = STATUS_PROCESSING
        return ProcessingClaim(bid, DECISION_RETRY)

    def mark_processed(self, bid):
        self.by_id[bid]["status"] = STATUS_PROCESSED

    def mark_rejected(self, bid, err):
        self.by_id[bid]["status"] = STATUS_REJECTED

    def record_transient_error(self, bid, err):
        self.by_id[bid]["status"] = STATUS_RECEIVED


def _mock_service():
    subs = MemSubRepo()
    events = MemEventRepo()
    provider = MockPaymentProvider()
    return BillingService(subscription_repo=subs, event_repo=events, provider=provider), subs, events, provider


# --------------------------------------------------------------------------
# Checkout URL contract
# --------------------------------------------------------------------------

def test_mock_checkout_session_exposes_checkout_url() -> None:
    svc, subs, events, provider = _mock_service()
    session = svc.start_checkout(account_id="a", plan_code="pro")
    d = session.to_public_dict()
    assert "checkout_url" in d and d["checkout_url"].startswith("https://mock-checkout.local/")
    # No provider internal ids in the member-facing checkout payload.
    for banned in ("customer", "provider_customer_id", "provider_subscription_id", "secret"):
        assert banned not in d


def test_start_checkout_denies_free_and_enterprise() -> None:
    svc, subs, events, provider = _mock_service()
    with pytest.raises(BillingError):
        svc.start_checkout(account_id="a", plan_code="free")
    with pytest.raises(BillingError):
        svc.start_checkout(account_id="a", plan_code="enterprise")
    with pytest.raises(BillingError):
        svc.start_checkout(account_id="a", plan_code="platinum")


# --------------------------------------------------------------------------
# Cancellation (provider-neutral, no local fake)
# --------------------------------------------------------------------------

def _activate(svc, subs, provider, account_id, plan="pro"):
    e = provider.make_event(account_id=account_id, event_type=EVENT_CHECKOUT_COMPLETED, target_plan_code=plan)
    svc.process_provider_event(e)


def test_cancellation_requests_provider_without_faking_state() -> None:
    svc, subs, _, provider = _mock_service()
    _activate(svc, subs, provider, "acct_c")
    assert subs.get_by_account("acct_c").status == "active"
    result = svc.request_cancellation(account_id="acct_c")
    assert result["status"] == "cancellation_requested"
    assert result["cancel_at_period_end"] is True
    # No local fake lifecycle change: still active until a verified webhook.
    assert subs.get_by_account("acct_c").status == "active"
    assert subs.get_by_account("acct_c").cancel_at_period_end is True
    # Paid entitlements still follow backend state (active) until webhook.
    assert resolve_entitlements(subs.get_by_account("acct_c")).has("advanced_signals") is True


def test_cancellation_missing_subscription_is_safe() -> None:
    svc, subs, _, provider = _mock_service()
    result = svc.request_cancellation(account_id="acct_none")
    assert result["status"] == "no_active_subscription"
    assert result["cancel_at_period_end"] is False


def test_webhook_deletion_after_cancel_request_finalizes_state() -> None:
    svc, subs, _, provider = _mock_service()
    _activate(svc, subs, provider, "acct_f")
    svc.request_cancellation(account_id="acct_f")
    # The authoritative canceled state arrives as a provider event.
    from backend.nexus_billing.provider import EVENT_SUBSCRIPTION_CANCELED
    svc.process_provider_event(provider.make_event(account_id="acct_f", event_type=EVENT_SUBSCRIPTION_CANCELED))
    assert subs.get_by_account("acct_f").status == "canceled"
    assert resolve_entitlements(subs.get_by_account("acct_f")).has("advanced_signals") is False


def test_cancel_flag_is_provider_authoritative_not_cleared_by_recovery() -> None:
    svc, subs, _, provider = _mock_service()
    _activate(svc, subs, provider, "acct_r")
    svc.request_cancellation(account_id="acct_r")
    assert subs.get_by_account("acct_r").cancel_at_period_end is True
    # Payment failure + recovery does NOT by itself clear a scheduled cancel.
    from backend.nexus_billing.provider import (
        EVENT_PAYMENT_FAILED,
        EVENT_PAYMENT_RECOVERED,
        EVENT_SUBSCRIPTION_ACTIVE,
        ProviderEvent,
    )
    svc.process_provider_event(provider.make_event(account_id="acct_r", event_type=EVENT_PAYMENT_FAILED))
    svc.process_provider_event(provider.make_event(account_id="acct_r", event_type=EVENT_PAYMENT_RECOVERED))
    assert subs.get_by_account("acct_r").status == "active"
    assert subs.get_by_account("acct_r").cancel_at_period_end is True  # still scheduled
    # Only an explicit provider signal (cancel_at_period_end=False) clears it.
    resume = ProviderEvent(provider="mock", provider_event_id="resume_1",
                           event_type=EVENT_SUBSCRIPTION_ACTIVE, account_id="acct_r",
                           target_plan_code="pro", cancel_at_period_end=False)
    svc.process_provider_event(resume)
    assert subs.get_by_account("acct_r").cancel_at_period_end is False


def test_portal_session_is_member_safe() -> None:
    svc, subs, _, provider = _mock_service()
    _activate(svc, subs, provider, "acct_p")
    portal = svc.create_billing_portal(account_id="acct_p")
    d = portal.to_public_dict()
    assert d["portal_url"].startswith("https://mock-portal.local/")
    assert "secret" not in d


# --------------------------------------------------------------------------
# HTTP routes (auth, session-derived account, gating)
# --------------------------------------------------------------------------

class FakeAuth:
    def __init__(self):
        self.sessions = {}

    def resolve_session(self, sid):
        aid = self.sessions.get(sid)
        return {"account_id": aid} if aid else None


def _app(mock_enabled=True):
    app = Flask(__name__)
    app.config["TESTING"] = True
    auth = FakeAuth()
    svc, subs, events, provider = _mock_service()
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    app.config[BILLING_SERVICE_CONFIG_KEY] = svc
    app.config[MOCK_ENABLED_CONFIG_KEY] = mock_enabled
    register_billing_routes(app)
    return app, auth, subs, svc, provider


def test_cancel_route_requires_auth() -> None:
    app, auth, subs, svc, provider = _app()
    assert app.test_client().post("/api/v1/billing/cancel").status_code == 401


def test_cancel_route_uses_session_account_only() -> None:
    app, auth, subs, svc, provider = _app()
    auth.sessions["sid"] = "acct_me"
    _activate(svc, subs, provider, "acct_me")
    _activate(svc, subs, provider, "acct_other")
    r = app.test_client().post("/api/v1/billing/cancel",
                               json={"account_id": "acct_other"}, headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 200
    # Only the session's own subscription is affected.
    assert subs.get_by_account("acct_me").cancel_at_period_end is True
    assert subs.get_by_account("acct_other").cancel_at_period_end is False


def test_cancel_route_unavailable_without_provider() -> None:
    app = Flask(__name__)
    app.config["TESTING"] = True
    auth = FakeAuth()
    auth.sessions["sid"] = "a"
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    app.config[MOCK_ENABLED_CONFIG_KEY] = False  # no mock, no stripe
    register_billing_routes(app)
    r = app.test_client().post("/api/v1/billing/cancel", headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 503


def test_mock_checkout_route_returns_checkout_url() -> None:
    app, auth, subs, svc, provider = _app()
    auth.sessions["sid"] = "acct_1"
    r = app.test_client().post("/api/v1/billing/mock/checkout", json={"plan_code": "pro"},
                               headers={"X-Nexus-Session": "sid"})
    body = r.get_json()["checkout"]
    assert body["checkout_url"].startswith("https://mock-checkout.local/")
    assert body["target_plan_code"] == "pro"


def test_portal_route_requires_auth_and_returns_url() -> None:
    app, auth, subs, svc, provider = _app()
    assert app.test_client().post("/api/v1/billing/portal").status_code == 401
    auth.sessions["sid"] = "acct_1"
    _activate(svc, subs, provider, "acct_1")
    r = app.test_client().post("/api/v1/billing/portal", headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 200
    assert r.get_json()["portal"]["portal_url"].startswith("https://mock-portal.local/")


def test_cancel_does_not_change_trading_or_entitlement_immediately() -> None:
    app, auth, subs, svc, provider = _app()
    auth.sessions["sid"] = "acct_1"
    _activate(svc, subs, provider, "acct_1", plan="advanced")
    app.test_client().post("/api/v1/billing/cancel", headers={"X-Nexus-Session": "sid"})
    ent = set(resolve_entitlements(subs.get_by_account("acct_1")).entitlements)
    banned = {"trading", "auto_trade", "order_execution", "exchange_write", "live_trading", "arm"}
    assert not (ent & banned)
    # still active -> paid entitlements remain until a verified webhook
    assert "premium_intelligence" in ent
