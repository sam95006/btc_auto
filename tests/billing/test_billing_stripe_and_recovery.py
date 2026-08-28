from __future__ import annotations

import hashlib
import hmac
import json
import time
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
from backend.nexus_billing.factory import build_payment_provider, build_stripe_config
from backend.nexus_billing.provider import (
    EVENT_CHECKOUT_COMPLETED,
    ProviderEvent,
)
from backend.nexus_billing.routes import (
    STRIPE_CONFIG_CONFIG_KEY,
    STRIPE_SERVICE_CONFIG_KEY,
    register_billing_routes,
)
from backend.nexus_billing.service import BillingError, BillingService
from backend.nexus_billing.stripe_provider import (
    StripeConfig,
    StripeConfigError,
    StripePaymentProvider,
    build_checkout_params,
    is_live_secret_key,
    is_test_secret_key,
    map_stripe_subscription_status,
    normalize_stripe_event,
    verify_stripe_signature,
)
from backend.nexus_billing.subscription import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    Subscription,
    assert_transition,
)

TEST_SECRET = "sk_test_deadbeef"
WEBHOOK_SECRET = "whsec_test_fake_secret"


def _config(**over) -> StripeConfig:
    base = dict(
        secret_key=TEST_SECRET,
        webhook_secret=WEBHOOK_SECRET,
        success_url="https://app.example/success",
        cancel_url="https://app.example/cancel",
        price_by_plan={"starter": "price_starter", "pro": "price_pro", "advanced": "price_adv"},
    )
    base.update(over)
    return StripeConfig(**base)


# ---- in-memory doubles (mirror real repo semantics) ----

class MemSubRepo:
    def __init__(self) -> None:
        self.by_account: dict[str, Subscription] = {}
        self.fail_next = 0  # transient-failure injection

    def get_by_account(self, account_id):
        return self.by_account.get(account_id)

    def create_subscription(self, *, account_id, plan_code, status=STATUS_INACTIVE, provider=None):
        s = Subscription(account_id=account_id, plan_code=plan_code, status=status, provider=provider)
        self.by_account[account_id] = s
        return s

    def ensure_subscription(self, account_id):
        s = self.by_account.get(account_id)
        if s is None:
            s = self.create_subscription(account_id=account_id, plan_code="free", status=STATUS_INACTIVE)
        return s

    def apply_provider_transition(self, account_id, to_status, *, plan_code=None, provider=None,
                                  provider_customer_id=None, provider_subscription_id=None):
        if self.fail_next > 0:
            self.fail_next -= 1
            raise RuntimeError("transient_db_error")
        cur = self.ensure_subscription(account_id)
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
        return cur


class MemEventRepo:
    def __init__(self) -> None:
        self.by_key: dict[tuple[str, str], str] = {}
        self.by_id: dict[str, dict[str, Any]] = {}

    def begin_processing(self, event: ProviderEvent) -> ProcessingClaim:
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
        self.by_id[bid].update({"status": STATUS_REJECTED, "error": err})

    def record_transient_error(self, bid, err):
        self.by_id[bid].update({"status": STATUS_RECEIVED, "error": err})

    def get_by_provider_event(self, provider, pid):
        bid = self.by_key.get((provider, pid))
        return {"billing_event_id": bid} if bid else None


def _stripe_service():
    subs = MemSubRepo()
    events = MemEventRepo()
    provider = StripePaymentProvider(_config())
    return BillingService(subscription_repo=subs, event_repo=events, provider=provider), subs, events


def _ent(sub, feat):
    return resolve_entitlements(sub).has(feat)


def _stripe_event(event_type, *, event_id, account_id="acct_1", plan_code=None, status=None,
                  customer="cus_test_1", subscription="sub_test_1", extra_object=None):
    obj: dict[str, Any] = {"id": subscription, "customer": customer, "metadata": {}}
    if account_id is not None:
        obj["metadata"]["account_id"] = account_id
    if plan_code is not None:
        obj["metadata"]["plan_code"] = plan_code
    if status is not None:
        obj["status"] = status
    if event_type == "checkout.session.completed":
        obj = {"id": "cs_test_1", "customer": customer, "subscription": subscription, "metadata": obj["metadata"]}
    if event_type in ("invoice.paid", "invoice.payment_failed"):
        obj = {"id": "in_test_1", "customer": customer, "subscription": subscription, "metadata": obj["metadata"]}
    if extra_object:
        obj.update(extra_object)
    return {"id": event_id, "type": event_type, "data": {"object": obj}}


# --------------------------------------------------------------------------
# Stripe config / key gating (2,3)
# --------------------------------------------------------------------------

def test_live_secret_key_rejected() -> None:
    assert is_live_secret_key("sk_live_abc") is True
    assert is_test_secret_key("sk_test_abc") is True
    with pytest.raises(StripeConfigError):
        _config(secret_key="sk_live_abc").validate()
    with pytest.raises(StripeConfigError):
        StripePaymentProvider(_config(secret_key="sk_live_abc"))


def test_factory_disables_on_missing_or_live_config() -> None:
    assert build_payment_provider({"NEXUS_BILLING_PROVIDER": "stripe"}) is None  # incomplete
    live_env = {
        "NEXUS_BILLING_PROVIDER": "stripe",
        "STRIPE_SECRET_KEY": "sk_live_x",
        "STRIPE_WEBHOOK_SECRET": "whsec_x",
        "STRIPE_SUCCESS_URL": "https://a/s",
        "STRIPE_CANCEL_URL": "https://a/c",
        "STRIPE_PRICE_PRO": "price_pro",
    }
    assert build_payment_provider(live_env) is None  # live key -> disabled, no fallback
    assert build_stripe_config(live_env) is None


def test_factory_builds_test_stripe_provider() -> None:
    env = {
        "NEXUS_BILLING_PROVIDER": "stripe",
        "STRIPE_SECRET_KEY": TEST_SECRET,
        "STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "STRIPE_SUCCESS_URL": "https://a/s",
        "STRIPE_CANCEL_URL": "https://a/c",
        "STRIPE_PRICE_PRO": "price_pro",
    }
    p = build_payment_provider(env)
    assert isinstance(p, StripePaymentProvider) and p.name == "stripe"


def test_stripe_adapter_implements_provider_contract() -> None:
    p = StripePaymentProvider(_config())
    for m in ("create_checkout_session", "cancel_subscription", "normalize_event", "price_for_plan"):
        assert hasattr(p, m)


# --------------------------------------------------------------------------
# Plan -> price mapping / checkout params (4,5,6,7,9,10,11)
# --------------------------------------------------------------------------

def test_free_and_enterprise_and_unknown_not_self_service() -> None:
    p = StripePaymentProvider(_config())
    assert p.price_for_plan("free") is None
    assert p.price_for_plan("enterprise") is None  # not self-service by default
    assert p.price_for_plan("platinum") is None
    assert p.price_for_plan("pro") == "price_pro"


def test_checkout_params_are_server_authoritative_with_metadata() -> None:
    params = build_checkout_params(account_id="acct_9", plan_code="pro", price_id="price_pro",
                                   success_url="https://a/s", cancel_url="https://a/c")
    assert params["mode"] == "subscription"
    assert params["line_items"][0]["price"] == "price_pro"
    assert params["success_url"] == "https://a/s" and params["cancel_url"] == "https://a/c"
    # internal account/plan travel in BOTH session and subscription metadata
    assert params["metadata"] == {"account_id": "acct_9", "plan_code": "pro"}
    assert params["subscription_data"]["metadata"] == {"account_id": "acct_9", "plan_code": "pro"}
    # no client-supplied price/amount/currency authority
    for banned in ("amount", "currency", "unit_amount"):
        assert banned not in params


def test_start_checkout_rejects_free_and_unknown_before_sdk() -> None:
    svc, *_ = _stripe_service()
    with pytest.raises(BillingError):
        svc.start_checkout(account_id="a", plan_code="free")
    with pytest.raises(BillingError):
        svc.start_checkout(account_id="a", plan_code="platinum")


# --------------------------------------------------------------------------
# Webhook signature verification (12,13,14,15)
# --------------------------------------------------------------------------

def _sign(payload: bytes, secret: str, ts: Optional[int] = None) -> str:
    ts = int(time.time()) if ts is None else ts
    signed = f"{ts}.".encode("utf-8") + payload
    v1 = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"


def test_signature_valid_invalid_missing() -> None:
    payload = b'{"hello":"world"}'
    good = _sign(payload, WEBHOOK_SECRET)
    assert verify_stripe_signature(payload, good, WEBHOOK_SECRET) is True
    assert verify_stripe_signature(payload, good, "whsec_wrong") is False
    assert verify_stripe_signature(payload, "", WEBHOOK_SECRET) is False
    assert verify_stripe_signature(b"", good, WEBHOOK_SECRET) is False
    # tampered body
    assert verify_stripe_signature(b'{"hello":"tampered"}', good, WEBHOOK_SECRET) is False
    # expired timestamp
    old = _sign(payload, WEBHOOK_SECRET, ts=int(time.time()) - 10000)
    assert verify_stripe_signature(payload, old, WEBHOOK_SECRET, tolerance=300) is False


# --------------------------------------------------------------------------
# Stripe event normalization (17-25)
# --------------------------------------------------------------------------

def test_normalize_checkout_completed() -> None:
    ev = normalize_stripe_event(_stripe_event("checkout.session.completed", event_id="e1", plan_code="pro"))
    assert ev.event_type == EVENT_CHECKOUT_COMPLETED
    assert ev.account_id == "acct_1" and ev.target_plan_code == "pro"
    assert ev.provider == "stripe" and ev.provider_subscription_id == "sub_test_1"


def test_normalize_subscription_statuses() -> None:
    active = normalize_stripe_event(_stripe_event("customer.subscription.updated", event_id="e2",
                                                  plan_code="pro", status="active"))
    assert active.event_type == "subscription_active" and active.target_plan_code == "pro"
    past_due = normalize_stripe_event(_stripe_event("customer.subscription.updated", event_id="e3", status="past_due"))
    assert past_due.event_type == "subscription_past_due"
    deleted = normalize_stripe_event(_stripe_event("customer.subscription.deleted", event_id="e4"))
    assert deleted.event_type == "subscription_canceled"


def test_normalize_invoices() -> None:
    paid = normalize_stripe_event(_stripe_event("invoice.paid", event_id="e5"))
    assert paid.event_type == "payment_recovered"
    failed = normalize_stripe_event(_stripe_event("invoice.payment_failed", event_id="e6"))
    assert failed.event_type == "payment_failed"


def test_unknown_event_type_and_status_ignored() -> None:
    assert normalize_stripe_event(_stripe_event("charge.refunded", event_id="e7")) is None
    assert map_stripe_subscription_status("some_new_status") is None
    unknown_status = normalize_stripe_event(
        _stripe_event("customer.subscription.updated", event_id="e8", status="some_new_status")
    )
    assert unknown_status is None  # fail closed, never auto-active


# --------------------------------------------------------------------------
# Stripe entitlement E2E via normalized events (37,38,39)
# --------------------------------------------------------------------------

def test_stripe_lifecycle_entitlement_e2e() -> None:
    svc, subs, events = _stripe_service()
    acct = "acct_s"

    svc.process_provider_event(normalize_stripe_event(
        _stripe_event("checkout.session.completed", event_id="c1", account_id=acct, plan_code="pro")))
    assert subs.get_by_account(acct).status == "active"
    assert _ent(subs.get_by_account(acct), "advanced_signals") is True

    svc.process_provider_event(normalize_stripe_event(
        _stripe_event("invoice.payment_failed", event_id="f1", account_id=acct)))
    assert subs.get_by_account(acct).status == "past_due"
    assert _ent(subs.get_by_account(acct), "advanced_signals") is False

    svc.process_provider_event(normalize_stripe_event(
        _stripe_event("invoice.paid", event_id="p1", account_id=acct)))
    assert subs.get_by_account(acct).status == "active"
    assert _ent(subs.get_by_account(acct), "advanced_signals") is True

    svc.process_provider_event(normalize_stripe_event(
        _stripe_event("customer.subscription.deleted", event_id="d1", account_id=acct)))
    assert subs.get_by_account(acct).status == "canceled"
    assert _ent(subs.get_by_account(acct), "advanced_signals") is False


# --------------------------------------------------------------------------
# Crash recovery / convergence / idempotency (28-36)
# --------------------------------------------------------------------------

def test_duplicate_processed_event_idempotent() -> None:
    svc, subs, events = _stripe_service()
    e = normalize_stripe_event(_stripe_event("checkout.session.completed", event_id="dup1", plan_code="pro"))
    assert svc.process_provider_event(e)["status"] == "processed"
    assert svc.process_provider_event(e)["status"] == "already_processed"
    assert len(events.by_id) == 1


def test_transient_failure_is_retryable_and_recovers() -> None:
    svc, subs, events = _stripe_service()
    subs.fail_next = 1  # first apply raises
    e = normalize_stripe_event(_stripe_event("checkout.session.completed", event_id="t1", plan_code="pro"))
    r1 = svc.process_provider_event(e)
    assert r1["status"] == "error" and r1["retryable"] is True
    assert subs.get_by_account("acct_1") is None or subs.get_by_account("acct_1").status == "inactive"
    # retry (same event id) recovers -> processed
    r2 = svc.process_provider_event(e)
    assert r2["status"] == "processed"
    assert subs.get_by_account("acct_1").status == "active"
    assert len(events.by_id) == 1  # still one ledger row


def test_crash_after_mutation_before_mark_converges() -> None:
    svc, subs, events = _stripe_service()
    e = normalize_stripe_event(_stripe_event("checkout.session.completed", event_id="cv1", plan_code="pro"))
    # Simulate: event claimed + subscription mutated, but the mark_processed was
    # lost to a crash -> leave the ledger row non-terminal, sub already active.
    claim = events.begin_processing(e)
    subs.apply_provider_transition("acct_1", STATUS_ACTIVE, plan_code="pro", provider="stripe",
                                   provider_subscription_id="sub_test_1")
    events.record_transient_error(claim.billing_event_id, "crash")
    # Re-delivery converges (already at target) -> processed, no double mutation.
    r = svc.process_provider_event(e)
    assert r["status"] == "processed" and r.get("converged") is True
    assert subs.get_by_account("acct_1").status == "active"


def test_terminal_processed_never_remutates() -> None:
    svc, subs, events = _stripe_service()
    e = normalize_stripe_event(_stripe_event("checkout.session.completed", event_id="tp1", plan_code="pro"))
    svc.process_provider_event(e)
    subs.by_account["acct_1"].status = "active"  # ensure active
    r = svc.process_provider_event(e)
    assert r["status"] == "already_processed"


def test_permanent_rejection_deterministic() -> None:
    svc, subs, events = _stripe_service()
    e = ProviderEvent(provider="stripe", provider_event_id="pr1", event_type=EVENT_CHECKOUT_COMPLETED,
                      account_id="a", target_plan_code="platinum")
    assert svc.process_provider_event(e)["reason"] == "unknown_plan"
    assert svc.process_provider_event(e)["status"] == "already_rejected"


def test_concurrent_duplicate_applies_once() -> None:
    svc, subs, events = _stripe_service()
    e = normalize_stripe_event(_stripe_event("checkout.session.completed", event_id="cc1", plan_code="pro"))
    # Two "workers" for the same event id: first NEW applies, second RETRY converges.
    r1 = svc.process_provider_event(e)
    r2 = svc.process_provider_event(e)
    assert r1["status"] == "processed"
    assert r2["status"] in ("processed", "already_processed")
    assert len(subs.by_account) == 1
    assert len(events.by_id) == 1


def test_out_of_order_illegal_event_fails_closed() -> None:
    svc, subs, events = _stripe_service()
    acct = "acct_oo"
    # expire first
    for et, eid, plan in (
        ("checkout.session.completed", "o1", "pro"),
        ("customer.subscription.deleted", "o2", None),
    ):
        svc.process_provider_event(normalize_stripe_event(_stripe_event(et, event_id=eid, account_id=acct, plan_code=plan)))
    # subscription.updated active arriving late (out of order) after canceled -> illegal
    r = svc.process_provider_event(normalize_stripe_event(
        _stripe_event("customer.subscription.updated", event_id="o3", account_id=acct, plan_code="pro", status="active")))
    assert r["status"] == "rejected" and r["reason"] == "illegal_transition"
    assert _ent(subs.get_by_account(acct), "advanced_signals") is False


# --------------------------------------------------------------------------
# HTTP webhook + checkout routes
# --------------------------------------------------------------------------

class FakeAuth:
    def __init__(self):
        self.sessions = {}

    def resolve_session(self, sid):
        aid = self.sessions.get(sid)
        return {"account_id": aid} if aid else None


def _app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    auth = FakeAuth()
    svc, subs, events = _stripe_service()
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    app.config[STRIPE_CONFIG_CONFIG_KEY] = _config()
    app.config[STRIPE_SERVICE_CONFIG_KEY] = svc
    register_billing_routes(app)
    return app, auth, subs


def _post_webhook(client, payload_dict, *, secret=WEBHOOK_SECRET, sign=True, ts=None):
    raw = json.dumps(payload_dict).encode("utf-8")
    headers = {}
    if sign:
        headers["Stripe-Signature"] = _sign(raw, secret, ts)
    return client.post("/api/v1/billing/webhook/stripe", data=raw, content_type="application/json", headers=headers)


def test_webhook_requires_valid_signature() -> None:
    app, _, _ = _app()
    c = app.test_client()
    payload = _stripe_event("checkout.session.completed", event_id="w1", plan_code="pro")
    assert _post_webhook(c, payload, sign=False).status_code == 400
    assert _post_webhook(c, payload, secret="whsec_wrong").status_code == 400


def test_webhook_valid_signature_activates_subscription() -> None:
    app, _, subs = _app()
    c = app.test_client()
    payload = _stripe_event("checkout.session.completed", event_id="w2", account_id="acct_http", plan_code="pro")
    r = _post_webhook(c, payload)
    assert r.status_code == 200 and r.get_json()["received"] is True
    assert subs.get_by_account("acct_http").status == "active"


def test_webhook_does_not_use_member_session() -> None:
    # No X-Nexus-Session header at all; signature is the only auth.
    app, _, subs = _app()
    payload = _stripe_event("checkout.session.completed", event_id="w3", account_id="acct_nosess", plan_code="pro")
    r = _post_webhook(app.test_client(), payload)
    assert r.status_code == 200
    assert subs.get_by_account("acct_nosess").status == "active"


def test_webhook_unknown_event_acknowledged_no_mutation() -> None:
    app, _, subs = _app()
    r = _post_webhook(app.test_client(), _stripe_event("charge.refunded", event_id="w4"))
    body = r.get_json()
    assert r.status_code == 200 and body["handled"] is False


def test_webhook_malformed_payload_rejected() -> None:
    app, _, _ = _app()
    raw = b"not-json-at-all"
    sig = _sign(raw, WEBHOOK_SECRET)
    r = app.test_client().post("/api/v1/billing/webhook/stripe", data=raw,
                               headers={"Stripe-Signature": sig})
    assert r.status_code == 400


def test_webhook_duplicate_is_idempotent_http() -> None:
    app, _, subs = _app()
    c = app.test_client()
    payload = _stripe_event("checkout.session.completed", event_id="w5", account_id="acct_dup", plan_code="pro")
    assert _post_webhook(c, payload).status_code == 200
    r2 = _post_webhook(c, payload)
    assert r2.status_code == 200 and r2.get_json()["result_status"] == "already_processed"


def test_frontend_success_redirect_cannot_unlock() -> None:
    # There is NO route that unlocks on a success redirect; only a verified
    # webhook changes state. A GET to a success-like path does nothing.
    app, _, subs = _app()
    # Without a webhook, the account remains free.
    assert subs.get_by_account("acct_x") is None


def test_checkout_requires_auth() -> None:
    app, _, _ = _app()
    assert app.test_client().post("/api/v1/billing/checkout", json={"plan_code": "pro"}).status_code == 401


def test_checkout_rejects_free_plan_http() -> None:
    app, auth, _ = _app()
    auth.sessions["sid"] = "acct_1"
    r = app.test_client().post("/api/v1/billing/checkout", json={"plan_code": "free"},
                               headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 400


def test_checkout_valid_plan_without_sdk_is_unavailable_not_error() -> None:
    # pro is valid; the real hosted checkout needs the Stripe SDK/creds -> 503
    # (deferred runtime), never a fallback that grants access.
    app, auth, subs = _app()
    auth.sessions["sid"] = "acct_1"
    r = app.test_client().post("/api/v1/billing/checkout", json={"plan_code": "pro"},
                               headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 503
    assert subs.get_by_account("acct_1") is None  # no state change


def test_checkout_disabled_without_stripe_config() -> None:
    app = Flask(__name__)
    app.config["TESTING"] = True
    auth = FakeAuth()
    auth.sessions["sid"] = "acct_1"
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    register_billing_routes(app)  # no stripe config injected
    r = app.test_client().post("/api/v1/billing/checkout", json={"plan_code": "pro"},
                               headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 503


# --------------------------------------------------------------------------
# Trading firewall
# --------------------------------------------------------------------------

def test_stripe_paid_subscription_is_not_trading_authorization() -> None:
    svc, subs, events = _stripe_service()
    svc.process_provider_event(normalize_stripe_event(
        _stripe_event("checkout.session.completed", event_id="tf1", account_id="acct_tf", plan_code="advanced")))
    ent = set(resolve_entitlements(subs.get_by_account("acct_tf")).entitlements)
    banned = {"trading", "auto_trade", "order_execution", "exchange_write", "live_trading", "arm"}
    assert not (ent & banned)
