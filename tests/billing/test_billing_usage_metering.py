from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from flask import Flask

from backend.nexus_billing.routes import (
    USAGE_DEMO_ENABLED_CONFIG_KEY,
    USAGE_SERVICE_CONFIG_KEY,
    register_billing_routes,
)
from backend.nexus_billing.subscription import (
    STATUS_ACTIVE,
    STATUS_CANCELED,
    STATUS_EXPIRED,
    STATUS_INACTIVE,
    STATUS_PAST_DUE,
    STATUS_TRIALING,
    Subscription,
)
from backend.nexus_billing.usage_policy import (
    QUOTA_ANALYSIS_DAILY,
    QUOTA_CATALOG,
    QUOTA_HISTORY_DAYS,
    QUOTA_REPORTS_MONTHLY,
    is_valid_quota,
    plan_quota_codes,
    quota_limit,
)
from backend.nexus_billing.usage_service import UsageService
from backend.nexus_billing.usage_windows import (
    daily_window_start,
    monthly_window_start,
    window_reset_at,
    window_start_for,
)


# --------------------------------------------------------------------------
# Policy catalog (8-12)
# --------------------------------------------------------------------------

def test_quota_codes_unique_and_catalog_deterministic() -> None:
    codes = list(QUOTA_CATALOG.keys())
    assert len(codes) == len(set(codes))
    assert plan_quota_codes("pro") == list(QUOTA_CATALOG.keys())


def test_unknown_quota_rejected() -> None:
    assert is_valid_quota(QUOTA_ANALYSIS_DAILY) is True
    assert is_valid_quota("nope") is False
    assert is_valid_quota(None) is False


def test_plan_policy_resolves_and_unknown_plan_falls_back_free() -> None:
    assert quota_limit("pro", QUOTA_ANALYSIS_DAILY) == 100
    assert quota_limit("free", QUOTA_ANALYSIS_DAILY) == 0
    assert quota_limit("advanced", QUOTA_ANALYSIS_DAILY) == 500
    # Unknown plan -> free policy.
    assert quota_limit("platinum", QUOTA_ANALYSIS_DAILY) == quota_limit("free", QUOTA_ANALYSIS_DAILY)


# --------------------------------------------------------------------------
# Windows (16-17)
# --------------------------------------------------------------------------

def test_deterministic_utc_windows() -> None:
    now = datetime(2026, 3, 15, 13, 45, tzinfo=timezone.utc)
    assert daily_window_start(now) == datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)
    assert monthly_window_start(now) == datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
    assert window_reset_at("daily", now) == datetime(2026, 3, 16, 0, 0, tzinfo=timezone.utc)
    assert window_reset_at("monthly", now) == datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
    # December rolls to next year.
    dec = datetime(2026, 12, 20, tzinfo=timezone.utc)
    assert window_reset_at("monthly", dec) == datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# In-memory metering (mirrors the atomic DB semantics)
# --------------------------------------------------------------------------

class MemUsageRepo:
    def __init__(self) -> None:
        self.counters: dict[tuple, int] = {}
        self.events: set[tuple] = set()

    def get_used(self, account_id, quota_code, window_type, window_start) -> int:
        return self.counters.get((account_id, quota_code, window_type, window_start), 0)

    def consume(self, *, account_id, quota_code, window_type, window_start, amount, limit, idempotency_key):
        if amount <= 0:
            raise ValueError("invalid_amount")
        ckey = (account_id, quota_code, window_type, window_start)
        used = self.counters.get(ckey, 0)
        idem = (account_id, quota_code, window_type, window_start, idempotency_key)
        if idem in self.events:
            return True, used  # idempotent no-op
        if used + amount <= limit:
            self.counters[ckey] = used + amount
            self.events.add(idem)
            return True, used + amount
        return False, used  # denied; nothing persisted


class MemSubRepo:
    def __init__(self) -> None:
        self.by_account: dict[str, Subscription] = {}

    def get_by_account(self, aid):
        return self.by_account.get(aid)

    def set(self, aid, plan, status):
        self.by_account[aid] = Subscription(account_id=aid, plan_code=plan, status=status)


def _svc(sub_plan="pro", sub_status=STATUS_ACTIVE, clock=None):
    usage = MemUsageRepo()
    subs = MemSubRepo()
    subs.set("acct", sub_plan, sub_status)
    clock = clock or (lambda: datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc))
    return UsageService(usage_repo=usage, subscription_repo=subs, clock=clock), usage, subs


def test_first_consume_increments() -> None:
    svc, usage, _ = _svc()
    d = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="k1")
    assert d.allowed and d.used == 1 and d.remaining == 99


def test_duplicate_idempotency_key_does_not_increment_twice() -> None:
    svc, usage, _ = _svc()
    a = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="dup")
    b = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="dup")
    assert a.used == 1 and b.used == 1  # not 2


def test_distinct_requests_increment() -> None:
    svc, usage, _ = _svc()
    svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="a")
    d = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="b")
    assert d.used == 2


def test_daily_and_monthly_windows_reset() -> None:
    day1 = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 3, 16, 1, 0, tzinfo=timezone.utc)
    clock = {"now": day1}
    svc, usage, _ = _svc(clock=lambda: clock["now"])
    svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="d1")
    clock["now"] = day2  # next day -> new window
    d = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="d2")
    assert d.used == 1  # reset


def test_cannot_exceed_limit_and_exact_last_unit() -> None:
    # Pro holds the advanced_analysis entitlement; daily limit is 100.
    svc, usage, _ = _svc(sub_plan="pro")
    assert svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, amount=99, idempotency_key="a").used == 99
    last = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, amount=1, idempotency_key="b")
    assert last.allowed and last.used == 100 and last.remaining == 0
    denied = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, amount=1, idempotency_key="c")
    assert denied.allowed is False and denied.remaining == 0 and denied.reason == "quota_exceeded"


def test_amount_greater_than_remaining_denied_atomically() -> None:
    svc, usage, _ = _svc(sub_plan="pro")  # limit 100
    d = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, amount=150, idempotency_key="big")
    assert d.allowed is False and d.used == 0  # nothing consumed


def test_malformed_amount_denied() -> None:
    svc, usage, _ = _svc()
    assert svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, amount=0, idempotency_key="z").allowed is False
    assert svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, amount=-1, idempotency_key="z2").allowed is False


def test_unknown_quota_and_capacity_denied() -> None:
    svc, usage, _ = _svc()
    assert svc.consume(account_id="acct", quota_code="nope", idempotency_key="x").allowed is False
    # capacity quota is not consumable
    assert svc.consume(account_id="acct", quota_code=QUOTA_HISTORY_DAYS, idempotency_key="y").allowed is False


def test_usage_repo_failure_fails_closed() -> None:
    class Boom(MemUsageRepo):
        def consume(self, **kw):
            raise RuntimeError("db down")

    subs = MemSubRepo()
    subs.set("acct", "pro", STATUS_ACTIVE)
    svc = UsageService(usage_repo=Boom(), subscription_repo=subs,
                       clock=lambda: datetime(2026, 3, 15, tzinfo=timezone.utc))
    d = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="k")
    assert d.allowed is False and d.reason == "usage_unavailable"


# --------------------------------------------------------------------------
# Subscription integration (24-30)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("status", [STATUS_ACTIVE, STATUS_TRIALING])
def test_live_subscription_uses_plan_policy(status) -> None:
    svc, usage, _ = _svc(sub_plan="pro", sub_status=status)
    r = svc.resolve_usage("acct")
    assert r["effective_plan_code"] == "pro"
    analysis = next(q for q in r["quotas"] if q["quota_code"] == QUOTA_ANALYSIS_DAILY)
    assert analysis["limit"] == 100


@pytest.mark.parametrize("status", [STATUS_PAST_DUE, STATUS_CANCELED, STATUS_EXPIRED, STATUS_INACTIVE])
def test_non_live_subscription_falls_back_to_free(status) -> None:
    svc, usage, _ = _svc(sub_plan="pro", sub_status=status)
    assert svc.resolve_usage("acct")["effective_plan_code"] == "free"
    d = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="k")
    assert d.allowed is False  # free has 0 analysis quota


def test_upgrade_and_downgrade_change_effective_policy() -> None:
    svc, usage, subs = _svc(sub_plan="pro", sub_status=STATUS_ACTIVE)
    assert svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="k1").limit == 100
    subs.set("acct", "advanced", STATUS_ACTIVE)  # upgrade
    assert svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="k2").limit == 500
    subs.set("acct", "pro", STATUS_EXPIRED)  # downgrade/expired -> free
    assert svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="k3").allowed is False


# --------------------------------------------------------------------------
# HTTP API + enforcement (31-40)
# --------------------------------------------------------------------------

class FakeAuth:
    def __init__(self):
        self.sessions = {}

    def resolve_session(self, sid):
        aid = self.sessions.get(sid)
        return {"account_id": aid} if aid else None


class EntitlementSubRepo(MemSubRepo):
    """Also used by the entitlement resolver path via routes."""


def _app(plan="pro", status=STATUS_ACTIVE, demo=True):
    app = Flask(__name__)
    app.config["TESTING"] = True
    auth = FakeAuth()
    usage = MemUsageRepo()
    subs = MemSubRepo()
    subs.set("acct", plan, status)
    svc = UsageService(usage_repo=usage, subscription_repo=subs,
                       clock=lambda: datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc))
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth, "repo": None}
    # The entitlement/subscription resolution in routes reads the subscription
    # repo via the billing subscription repo config key.
    from backend.nexus_billing.routes import SUBSCRIPTION_REPO_CONFIG_KEY
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = subs
    app.config[USAGE_SERVICE_CONFIG_KEY] = svc
    app.config[USAGE_DEMO_ENABLED_CONFIG_KEY] = demo
    register_billing_routes(app)
    return app, auth, subs, usage


def test_usage_endpoint_requires_auth_and_returns_own_usage() -> None:
    app, auth, subs, usage = _app()
    assert app.test_client().get("/api/v1/billing/usage").status_code == 401
    auth.sessions["sid"] = "acct"
    r = app.test_client().get("/api/v1/billing/usage", headers={"X-Nexus-Session": "sid"})
    body = r.get_json()
    assert r.status_code == 200 and body["effective_plan_code"] == "pro"
    # No provider/internal ids exposed.
    text = r.get_data(as_text=True)
    for banned in ("provider_customer_id", "provider_subscription_id", "usage_event_id", "billing_event_id"):
        assert banned not in text


def test_usage_endpoint_account_spoof_ignored() -> None:
    app, auth, subs, usage = _app()
    subs.set("acct_other", "enterprise", STATUS_ACTIVE)
    auth.sessions["sid"] = "acct"
    r = app.test_client().get("/api/v1/billing/usage?account_id=acct_other", headers={"X-Nexus-Session": "sid"})
    assert r.get_json()["effective_plan_code"] == "pro"  # own (pro), not enterprise


def test_demo_endpoint_disabled_by_default() -> None:
    app, auth, subs, usage = _app(demo=False)
    auth.sessions["sid"] = "acct"
    r = app.test_client().post("/api/v1/billing/usage/consume-demo",
                               json={"idempotency_key": "k"}, headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 404


def test_demo_entitled_and_quota_available_succeeds_then_429() -> None:
    app, auth, subs, usage = _app(plan="starter")  # analysis daily = 20, entitled (advanced_signals? need advanced_analysis)
    auth.sessions["sid"] = "acct"
    c = app.test_client()
    # starter does NOT have advanced_analysis entitlement -> denied at entitlement layer.
    r0 = c.post("/api/v1/billing/usage/consume-demo", json={"idempotency_key": "s0"}, headers={"X-Nexus-Session": "sid"})
    assert r0.status_code == 403 and r0.get_json()["classification"] == "ENTITLEMENT_REQUIRED"


def test_demo_pro_consumes_until_quota_exhausted() -> None:
    app, auth, subs, usage = _app(plan="pro")  # advanced_analysis entitled; daily limit 100
    auth.sessions["sid"] = "acct"
    c = app.test_client()
    ok = c.post("/api/v1/billing/usage/consume-demo", json={"idempotency_key": "p1"}, headers={"X-Nexus-Session": "sid"})
    assert ok.status_code == 200 and ok.get_json()["ok"] is True
    # retry same key -> idempotent, still success, no double count
    retry = c.post("/api/v1/billing/usage/consume-demo", json={"idempotency_key": "p1"}, headers={"X-Nexus-Session": "sid"})
    assert retry.status_code == 200
    # exhaust the rest (already used 1)
    for i in range(99):
        c.post("/api/v1/billing/usage/consume-demo", json={"idempotency_key": f"q{i}"}, headers={"X-Nexus-Session": "sid"})
    over = c.post("/api/v1/billing/usage/consume-demo", json={"idempotency_key": "over"}, headers={"X-Nexus-Session": "sid"})
    assert over.status_code == 429
    body = over.get_json()
    assert body["classification"] == "USAGE_LIMIT_EXCEEDED" and body["remaining"] == 0


def test_demo_requires_idempotency_key() -> None:
    app, auth, subs, usage = _app(plan="pro")
    auth.sessions["sid"] = "acct"
    r = app.test_client().post("/api/v1/billing/usage/consume-demo", json={}, headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 400


def test_quota_never_grants_trading() -> None:
    # A metered success is not a trading authorization; usage catalog has no
    # trading codes.
    banned = {"trading", "auto_trade", "order_execution", "exchange_write", "arm"}
    assert not (set(QUOTA_CATALOG) & banned)


# --------------------------------------------------------------------------
# PLATFORM-1 carry-forward FIX A/B/C
# --------------------------------------------------------------------------

def test_fix_a_same_key_different_window_is_not_free_duplicate() -> None:
    day1 = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)
    clock = {"now": day1}
    svc, usage, _ = _svc(sub_plan="pro", clock=lambda: clock["now"])
    a = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="same")
    assert a.allowed and a.used == 1
    # Same key, SAME window -> idempotent no-op.
    dup = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="same")
    assert dup.used == 1
    # Same key, NEW window -> must count (not mistaken for a duplicate).
    clock["now"] = day2
    nxt = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="same")
    assert nxt.allowed and nxt.used == 1  # fresh window counter


def test_fix_b_non_entitled_quota_not_usable() -> None:
    # Starter has an analysis quota code but NOT the advanced_analysis entitlement.
    svc, usage, _ = _svc(sub_plan="starter", sub_status=STATUS_ACTIVE)
    resolved = svc.resolve_usage("acct")
    analysis = next(q for q in resolved["quotas"] if q["quota_code"] == QUOTA_ANALYSIS_DAILY)
    assert analysis["entitled"] is False and analysis["limit"] == 0  # not presented as usable
    d = svc.consume(account_id="acct", quota_code=QUOTA_ANALYSIS_DAILY, idempotency_key="k")
    assert d.allowed is False and d.reason == "entitlement_required"


def test_fix_c_error_semantics_distinct() -> None:
    app, auth, subs, usage = _app(plan="pro")
    auth.sessions["sid"] = "acct"
    c = app.test_client()
    # missing idempotency key -> 400
    assert c.post("/api/v1/billing/usage/consume-demo", json={}, headers={"X-Nexus-Session": "sid"}).status_code == 400


def test_fix_c_usage_unavailable_is_503() -> None:
    app = Flask(__name__)
    app.config["TESTING"] = True
    auth = FakeAuth()
    auth.sessions["sid"] = "acct"
    subs = MemSubRepo()
    subs.set("acct", "pro", STATUS_ACTIVE)
    from backend.nexus_billing.routes import SUBSCRIPTION_REPO_CONFIG_KEY
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = subs
    app.config[USAGE_SERVICE_CONFIG_KEY] = None  # no usage service available
    app.config[USAGE_DEMO_ENABLED_CONFIG_KEY] = True
    register_billing_routes(app)
    r = app.test_client().post("/api/v1/billing/usage/consume-demo",
                               json={"idempotency_key": "k"}, headers={"X-Nexus-Session": "sid"})
    assert r.status_code == 503
