from __future__ import annotations

from typing import Any, Optional

import pytest
from flask import Flask

from backend.nexus_billing.entitlements import resolve_entitlements
from backend.nexus_billing.mock_provider import MockPaymentProvider
from backend.nexus_billing.plans import normalize_plan_code
from backend.nexus_billing.provider import (
    EVENT_CHECKOUT_COMPLETED,
    EVENT_PAYMENT_FAILED,
    EVENT_PAYMENT_RECOVERED,
    EVENT_SUBSCRIPTION_CANCELED,
    EVENT_SUBSCRIPTION_EXPIRED,
    ProviderEvent,
)
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


# ---- in-memory doubles mirroring the real repository semantics ----

class MemSubRepo:
    def __init__(self) -> None:
        self.by_account: dict[str, Subscription] = {}

    def get_by_account(self, account_id: str) -> Optional[Subscription]:
        return self.by_account.get(account_id)

    def create_subscription(self, *, account_id, plan_code, status=STATUS_INACTIVE, provider=None) -> Subscription:
        sub = Subscription(account_id=account_id, plan_code=plan_code, status=status, provider=provider)
        self.by_account[account_id] = sub
        return sub

    def ensure_subscription(self, account_id: str) -> Subscription:
        sub = self.by_account.get(account_id)
        if sub is None:
            sub = self.create_subscription(account_id=account_id, plan_code="free", status=STATUS_INACTIVE)
        return sub

    def apply_provider_transition(self, account_id, to_status, *, plan_code=None, provider=None,
                                  provider_customer_id=None, provider_subscription_id=None) -> Subscription:
        cur = self.ensure_subscription(account_id)
        assert_transition(cur.status, to_status)
        cur.status = to_status
        if plan_code is not None:
            cur.plan_code = normalize_plan_code(plan_code)
        if provider is not None:
            cur.provider = provider
        if provider_customer_id is not None:
            cur.provider_customer_id = provider_customer_id
        if provider_subscription_id is not None:
            cur.provider_subscription_id = provider_subscription_id
        return cur


class MemEventRepo:
    def __init__(self) -> None:
        self.by_key: dict[tuple[str, str], str] = {}
        self.by_id: dict[str, dict[str, Any]] = {}

    def claim_event(self, event: ProviderEvent) -> tuple[str, bool]:
        key = (event.provider, event.provider_event_id)
        if key in self.by_key:
            return self.by_key[key], False
        bid = f"be_{len(self.by_id) + 1}"
        self.by_key[key] = bid
        self.by_id[bid] = {"status": "received", "event_type": event.event_type}
        return bid, True

    def mark_processed(self, bid: str) -> None:
        self.by_id[bid]["status"] = "processed"

    def mark_rejected(self, bid: str, error_class: str) -> None:
        self.by_id[bid].update({"status": "rejected", "error": error_class})

    def get_by_provider_event(self, provider: str, provider_event_id: str):
        bid = self.by_key.get((provider, provider_event_id))
        return {"billing_event_id": bid} if bid else None


def _service() -> tuple[BillingService, MemSubRepo, MemEventRepo, MockPaymentProvider]:
    subs = MemSubRepo()
    events = MemEventRepo()
    provider = MockPaymentProvider()
    return BillingService(subscription_repo=subs, event_repo=events, provider=provider), subs, events, provider


def _ent(sub: Optional[Subscription], feature: str) -> bool:
    return resolve_entitlements(sub).has(feature)


# --------------------------------------------------------------------------
# Full lifecycle E2E (core PASS criteria)
# --------------------------------------------------------------------------

def test_full_billing_lifecycle_e2e() -> None:
    svc, subs, events, provider = _service()
    acct = "acct_e2e"

    # FREE: no subscription -> free entitlements
    assert _ent(subs.get_by_account(acct), "advanced_signals") is False

    # mock PRO checkout
    session = svc.start_checkout(account_id=acct, plan_code="pro")
    assert session.checkout_id.startswith("mock_checkout_")
    assert session.target_plan_code == "pro"

    # mock completion event -> ACTIVE / PRO
    e_checkout = provider.make_event(account_id=acct, event_type=EVENT_CHECKOUT_COMPLETED, target_plan_code="pro")
    r = svc.process_provider_event(e_checkout)
    assert r["status"] == "processed" and r["subscription_status"] == "active"
    sub = subs.get_by_account(acct)
    assert sub.status == "active" and sub.plan_code == "pro"
    assert _ent(sub, "advanced_signals") is True  # Pro entitlement unlocked
    # provider metadata associated internally
    assert sub.provider == "mock" and sub.provider_customer_id.startswith("mock_customer_")

    # mock payment failure -> PAST_DUE -> effective FREE entitlements
    e_fail = provider.make_event(account_id=acct, event_type=EVENT_PAYMENT_FAILED)
    assert svc.process_provider_event(e_fail)["subscription_status"] == "past_due"
    assert _ent(subs.get_by_account(acct), "advanced_signals") is False

    # mock recovery -> ACTIVE -> Pro restored
    e_rec = provider.make_event(account_id=acct, event_type=EVENT_PAYMENT_RECOVERED)
    assert svc.process_provider_event(e_rec)["subscription_status"] == "active"
    assert _ent(subs.get_by_account(acct), "advanced_signals") is True

    # mock cancellation -> CANCELED -> free
    e_cancel = provider.make_event(account_id=acct, event_type=EVENT_SUBSCRIPTION_CANCELED)
    assert svc.process_provider_event(e_cancel)["subscription_status"] == "canceled"
    assert _ent(subs.get_by_account(acct), "advanced_signals") is False

    # mock expiration -> EXPIRED -> remains free
    e_exp = provider.make_event(account_id=acct, event_type=EVENT_SUBSCRIPTION_EXPIRED)
    assert svc.process_provider_event(e_exp)["subscription_status"] == "expired"
    assert _ent(subs.get_by_account(acct), "advanced_signals") is False


# --------------------------------------------------------------------------
# Idempotency
# --------------------------------------------------------------------------

def test_duplicate_event_is_idempotent_no_double_mutation() -> None:
    svc, subs, events, provider = _service()
    acct = "acct_idem"
    e = provider.make_event(account_id=acct, event_type=EVENT_CHECKOUT_COMPLETED,
                            target_plan_code="pro", provider_event_id="evt_fixed_1")
    first = svc.process_provider_event(e)
    assert first["status"] == "processed"
    # Replay exact same event id.
    second = svc.process_provider_event(e)
    assert second["status"] == "already_processed"
    # No duplicate subscription; state unchanged.
    assert len(subs.by_account) == 1
    assert subs.get_by_account(acct).status == "active"
    # Ledger recorded exactly one event.
    assert len(events.by_id) == 1


def test_different_event_ids_processed_independently() -> None:
    svc, subs, events, provider = _service()
    acct = "acct_multi"
    e1 = provider.make_event(account_id=acct, event_type=EVENT_CHECKOUT_COMPLETED,
                             target_plan_code="pro", provider_event_id="evt_a")
    assert svc.process_provider_event(e1)["status"] == "processed"
    e2 = provider.make_event(account_id=acct, event_type=EVENT_PAYMENT_FAILED, provider_event_id="evt_b")
    assert svc.process_provider_event(e2)["status"] == "processed"
    assert len(events.by_id) == 2


# --------------------------------------------------------------------------
# Invalid / unsafe events
# --------------------------------------------------------------------------

def test_unsupported_event_type_rejected() -> None:
    svc, subs, events, _ = _service()
    e = ProviderEvent(provider="mock", provider_event_id="x1", event_type="bogus_type", account_id="a")
    r = svc.process_provider_event(e)
    assert r["status"] == "rejected" and r["reason"] == "unsupported_event_type"
    assert subs.get_by_account("a") is None or subs.get_by_account("a").status == "inactive"


def test_malformed_event_rejected() -> None:
    svc, *_ = _service()
    e = ProviderEvent(provider="mock", provider_event_id="", event_type="", account_id="a")
    assert svc.process_provider_event(e)["status"] == "rejected"


def test_illegal_transition_rejected_no_paid_access() -> None:
    svc, subs, events, provider = _service()
    acct = "acct_illegal"
    # Drive to expired first.
    for et, plan in (
        (EVENT_CHECKOUT_COMPLETED, "pro"),
        (EVENT_SUBSCRIPTION_CANCELED, None),
        (EVENT_SUBSCRIPTION_EXPIRED, None),
    ):
        svc.process_provider_event(provider.make_event(account_id=acct, event_type=et, target_plan_code=plan))
    assert subs.get_by_account(acct).status == "expired"
    # Now an activation event requires an illegal transition (expired -> active).
    r = svc.process_provider_event(
        provider.make_event(account_id=acct, event_type=EVENT_CHECKOUT_COMPLETED, target_plan_code="pro")
    )
    assert r["status"] == "rejected" and r["reason"] == "illegal_transition"
    assert subs.get_by_account(acct).status == "expired"  # unchanged
    assert _ent(subs.get_by_account(acct), "advanced_signals") is False


def test_provider_mismatch_rejected() -> None:
    svc, *_ = _service()
    e = ProviderEvent(provider="stripe", provider_event_id="s1", event_type=EVENT_CHECKOUT_COMPLETED,
                      account_id="a", target_plan_code="pro")
    assert svc.process_provider_event(e)["reason"] == "provider_mismatch"


def test_checkout_unknown_plan_rejected_at_event() -> None:
    svc, subs, *_ = _service()
    e = ProviderEvent(provider="mock", provider_event_id="u1", event_type=EVENT_CHECKOUT_COMPLETED,
                      account_id="a", target_plan_code="platinum")
    r = svc.process_provider_event(e)
    assert r["status"] == "rejected" and r["reason"] == "unknown_plan"


# --------------------------------------------------------------------------
# Checkout request validation (no client price authority)
# --------------------------------------------------------------------------

def test_start_checkout_rejects_unknown_and_free_plan() -> None:
    svc, *_ = _service()
    with pytest.raises(BillingError):
        svc.start_checkout(account_id="a", plan_code="platinum")
    with pytest.raises(BillingError):
        svc.start_checkout(account_id="a", plan_code="free")


def test_start_checkout_returns_opaque_mock_session() -> None:
    svc, *_ = _service()
    s = svc.start_checkout(account_id="a", plan_code="enterprise")
    d = s.to_public_dict()
    assert d["checkout_id"].startswith("mock_checkout_")
    assert d["target_plan_code"] == "enterprise"
    # No card/secret fields.
    for banned in ("card", "cvv", "secret", "api_key", "provider_customer_id"):
        assert banned not in d


# --------------------------------------------------------------------------
# Trading firewall
# --------------------------------------------------------------------------

def test_paid_subscription_is_not_trading_authorization() -> None:
    svc, subs, events, provider = _service()
    acct = "acct_trade"
    svc.process_provider_event(
        provider.make_event(account_id=acct, event_type=EVENT_CHECKOUT_COMPLETED, target_plan_code="enterprise")
    )
    res = resolve_entitlements(subs.get_by_account(acct))
    banned = {"trading", "auto_trade", "order_execution", "exchange_write", "live_trading", "arm"}
    assert not (set(res.entitlements) & banned)


# --------------------------------------------------------------------------
# HTTP mock route gating
# --------------------------------------------------------------------------

class FakeAuth:
    def __init__(self) -> None:
        self.sessions: dict[str, str] = {}

    def resolve_session(self, session_id: str):
        aid = self.sessions.get(session_id)
        return {"account_id": aid} if aid else None


def _app(mock_enabled: bool):
    app = Flask(__name__)
    app.config["TESTING"] = True
    auth = FakeAuth()
    svc, subs, events, provider = _service()
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    app.config[BILLING_SERVICE_CONFIG_KEY] = svc
    app.config[MOCK_ENABLED_CONFIG_KEY] = mock_enabled
    register_billing_routes(app)
    return app, auth, subs


def test_mock_routes_disabled_by_default() -> None:
    app, auth, _ = _app(mock_enabled=False)
    auth.sessions["sid"] = "acct_1"
    c = app.test_client()
    for path in ("/api/v1/billing/mock/checkout", "/api/v1/billing/mock/event", "/api/v1/billing/mock/cancel"):
        r = c.post(path, json={"plan_code": "pro", "event_type": EVENT_CHECKOUT_COMPLETED},
                   headers={"X-Nexus-Session": "sid"})
        assert r.status_code == 404


def test_mock_routes_require_auth_when_enabled() -> None:
    app, _, _ = _app(mock_enabled=True)
    r = app.test_client().post("/api/v1/billing/mock/checkout", json={"plan_code": "pro"})
    assert r.status_code == 401


def test_mock_flow_works_only_under_explicit_config_and_derives_account_from_session() -> None:
    app, auth, subs = _app(mock_enabled=True)
    auth.sessions["sid"] = "acct_http"
    c = app.test_client()
    # checkout
    r = c.post("/api/v1/billing/mock/checkout", json={"plan_code": "pro"}, headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 200 and r.get_json()["checkout"]["target_plan_code"] == "pro"
    # completion event — account comes from session, NOT from body.
    r = c.post("/api/v1/billing/mock/event",
               json={"event_type": EVENT_CHECKOUT_COMPLETED, "plan_code": "pro", "account_id": "acct_OTHER"},
               headers={"X-Nexus-Session": "sid"})
    assert r.get_json()["result"]["status"] == "processed"
    assert subs.get_by_account("acct_http").status == "active"
    assert subs.get_by_account("acct_OTHER") is None  # spoofed account never touched


def test_mock_event_rejects_unknown_type_http() -> None:
    app, auth, _ = _app(mock_enabled=True)
    auth.sessions["sid"] = "acct_1"
    r = app.test_client().post("/api/v1/billing/mock/event", json={"event_type": "nope"},
                               headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 400


def test_mock_checkout_unknown_plan_http_400() -> None:
    app, auth, _ = _app(mock_enabled=True)
    auth.sessions["sid"] = "acct_1"
    r = app.test_client().post("/api/v1/billing/mock/checkout", json={"plan_code": "platinum"},
                               headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 400
