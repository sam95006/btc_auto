from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from flask import Flask

from backend.nexus_billing.routes import (
    SUBSCRIPTION_REPO_CONFIG_KEY,
    USAGE_SERVICE_CONFIG_KEY,
    register_billing_routes,
)
from backend.nexus_billing.subscription import STATUS_ACTIVE, STATUS_EXPIRED, STATUS_INACTIVE, Subscription
from backend.nexus_billing.usage_service import UsageService
from backend.nexus_personal.analysis import AnalysisDataUnavailable, analyze_series, build_report
from backend.nexus_personal.product_access import PRODUCT_FEATURES, feature_entitlement
from backend.nexus_personal.routes import (
    MARKET_SOURCE_CONFIG_KEY,
    WATCHLIST_REPO_CONFIG_KEY,
    register_personal_routes,
)


class FakeAuth:
    def __init__(self):
        self.sessions = {}

    def resolve_session(self, sid):
        aid = self.sessions.get(sid)
        return {"account_id": aid} if aid else None


class MemSubRepo:
    def __init__(self):
        self.by_account = {}

    def get_by_account(self, aid):
        return self.by_account.get(aid)

    def set(self, aid, plan, status=STATUS_ACTIVE):
        self.by_account[aid] = Subscription(account_id=aid, plan_code=plan, status=status)


class MemUsageRepo:
    def __init__(self):
        self.counters = {}
        self.events = set()

    def get_used(self, account_id, quota_code, window_type, window_start):
        return self.counters.get((account_id, quota_code, window_type, window_start), 0)

    def consume(self, *, account_id, quota_code, window_type, window_start, amount, limit, idempotency_key):
        if amount <= 0:
            raise ValueError("invalid_amount")
        ckey = (account_id, quota_code, window_type, window_start)
        used = self.counters.get(ckey, 0)
        idem = (account_id, quota_code, window_type, window_start, idempotency_key)
        if idem in self.events:
            return True, used
        if used + amount <= limit:
            self.counters[ckey] = used + amount
            self.events.add(idem)
            return True, used + amount
        return False, used


class MemWatchlistRepo:
    """In-memory double whose try_add_symbol mirrors the atomic DB contract.

    A single threading.Lock serializes the check-then-insert critical section,
    exactly as SELECT ... FOR UPDATE serializes it in Postgres. This lets the
    concurrency tests prove the capacity invariant deterministically.
    """

    def __init__(self):
        import threading

        self.by_account: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def list_symbols(self, account_id):
        return list(self.by_account.get(account_id, []))

    def count(self, account_id):
        return len(self.by_account.get(account_id, []))

    def contains(self, account_id, symbol):
        return symbol.upper() in [s.upper() for s in self.by_account.get(account_id, [])]

    def try_add_symbol(self, account_id, symbol, capacity):
        symbol = symbol.upper()
        with self._lock:
            items = self.by_account.setdefault(account_id, [])
            if symbol in [s.upper() for s in items]:
                return "DUPLICATE"
            if len(items) >= max(0, int(capacity)):
                return "CAPACITY"
            items.append(symbol)
            return "ADDED"

    def remove_symbol(self, account_id, symbol):
        self.by_account[account_id] = [s for s in self.by_account.get(account_id, []) if s.upper() != symbol.upper()]

    def active_watchlist_count(self, account_id):
        return 1 if self.by_account.get(account_id) else 0


def _app(plan="pro", status=STATUS_ACTIVE, market=True):
    app = Flask(__name__)
    app.config["TESTING"] = True
    auth = FakeAuth()
    subs = MemSubRepo()
    subs.set("acct", plan, status)
    usage = MemUsageRepo()
    svc = UsageService(usage_repo=usage, subscription_repo=subs,
                       clock=lambda: datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc))
    wl = MemWatchlistRepo()
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = subs
    app.config[USAGE_SERVICE_CONFIG_KEY] = svc
    app.config[WATCHLIST_REPO_CONFIG_KEY] = wl
    if market:
        # Deterministic test market series (explicit fixture, not fake live data).
        app.config[MARKET_SOURCE_CONFIG_KEY] = lambda sym: [100.0, 101.0, 103.0, 102.5, 106.0]
    register_billing_routes(app)
    register_personal_routes(app)
    auth.sessions["sid"] = "acct"
    return app, auth, subs, wl


def _h():
    return {"X-Nexus-Session": "sid"}


# --------------------------------------------------------------------------
# Central mapping + analysis unit
# --------------------------------------------------------------------------

def test_feature_mapping_is_central() -> None:
    assert feature_entitlement("advanced_analysis") == "advanced_analysis"
    assert feature_entitlement("watchlists") == "watchlists"
    assert PRODUCT_FEATURES["report_generation"].quota_code == "report_generation_monthly"


def test_analyze_series_deterministic_member_safe() -> None:
    r = analyze_series("BTCUSDT", [100.0, 101.0, 103.0, 106.0])
    assert r["data_class"] == "MEMBER_SAFE_ANALYSIS" and r["trend"] == "up"
    for banned in ("order", "position", "routing", "arm", "execution", "size"):
        assert banned not in str(r).lower()
    with pytest.raises(AnalysisDataUnavailable):
        analyze_series("BTCUSDT", [])


# --------------------------------------------------------------------------
# Free
# --------------------------------------------------------------------------

def test_free_basic_allowed_paid_denied() -> None:
    app, *_ = _app(plan="free", status=STATUS_INACTIVE)
    c = app.test_client()
    feats = c.get("/api/v1/personal/features", headers=_h()).get_json()["features"]
    fmap = {f["key"]: f for f in feats}
    assert fmap["market_overview"]["entitled"] is True
    assert fmap["advanced_analysis"]["entitled"] is False and fmap["advanced_analysis"]["locked"] is True
    # paid actions denied at the backend (403), not just hidden.
    assert c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "k"}, headers=_h()).status_code == 403
    assert c.post("/api/v1/personal/report", json={"symbol": "BTC", "idempotency_key": "k"}, headers=_h()).status_code == 403
    assert c.get("/api/v1/personal/signals", headers=_h()).status_code == 403


# --------------------------------------------------------------------------
# Starter
# --------------------------------------------------------------------------

def test_starter_watchlist_and_history_but_no_analysis() -> None:
    app, auth, subs, wl = _app(plan="starter")
    c = app.test_client()
    assert c.get("/api/v1/personal/watchlist", headers=_h()).status_code == 200
    # history clamp: starter history_days = 30
    h = c.get("/api/v1/personal/history?symbol=BTC&days=1000", headers=_h()).get_json()
    assert h["effective_days"] == 30 and h["clamped"] is True
    # analysis is pro+ -> denied for starter
    assert c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "k"}, headers=_h()).status_code == 403


# --------------------------------------------------------------------------
# Pro metered actions
# --------------------------------------------------------------------------

def test_pro_analysis_consumes_quota_and_is_idempotent() -> None:
    app, *_ = _app(plan="pro")
    c = app.test_client()
    r1 = c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "a1"}, headers=_h())
    assert r1.status_code == 200
    body = r1.get_json()
    assert body["ok"] and body["analysis"]["data_class"] == "MEMBER_SAFE_ANALYSIS"
    assert body["remaining"] == 99
    # duplicate request id -> no double consume
    r2 = c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "a1"}, headers=_h())
    assert r2.get_json()["remaining"] == 99
    # distinct request -> consumes again
    r3 = c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "a2"}, headers=_h())
    assert r3.get_json()["remaining"] == 98


def test_pro_report_consumes_quota() -> None:
    app, *_ = _app(plan="pro")
    c = app.test_client()
    r = c.post("/api/v1/personal/report", json={"symbol": "BTC", "idempotency_key": "r1"}, headers=_h())
    body = r.get_json()
    assert r.status_code == 200 and body["report"]["data_class"] == "MEMBER_SAFE_REPORT"
    assert body["remaining"] == 19  # report_generation_monthly pro = 20


def test_analysis_market_unavailable_is_503_and_no_consume() -> None:
    app, auth, subs, wl = _app(plan="pro", market=False)
    c = app.test_client()
    r = c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "k"}, headers=_h())
    assert r.status_code == 503
    # quota not consumed -> a later call with data still has full remaining
    app.config[MARKET_SOURCE_CONFIG_KEY] = lambda s: [1.0, 2.0, 3.0]
    r2 = c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "k2"}, headers=_h())
    assert r2.get_json()["remaining"] == 99


def test_analysis_missing_idempotency_is_400() -> None:
    app, *_ = _app(plan="pro")
    r = app.test_client().post("/api/v1/personal/analysis", json={"symbol": "BTC"}, headers=_h())
    assert r.status_code == 400


def test_analysis_quota_exhausted_is_429() -> None:
    app, auth, subs, wl = _app(plan="pro")
    c = app.test_client()
    for i in range(100):
        assert c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": f"k{i}"}, headers=_h()).status_code == 200
    over = c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "over"}, headers=_h())
    assert over.status_code == 429 and over.get_json()["classification"] == "USAGE_LIMIT_EXCEEDED"


# --------------------------------------------------------------------------
# Watchlist capacity
# --------------------------------------------------------------------------

def test_watchlist_requires_auth() -> None:
    app, *_ = _app(plan="starter")
    assert app.test_client().get("/api/v1/personal/watchlist").status_code == 401


def test_watchlist_add_remove_duplicate_and_capacity() -> None:
    app, auth, subs, wl = _app(plan="starter")  # watchlist_items = 20
    c = app.test_client()
    a = c.post("/api/v1/personal/watchlist", json={"symbol": "btc"}, headers=_h())
    assert a.status_code == 200 and a.get_json()["symbols"] == ["BTC"]
    # duplicate safe (idempotent, no error)
    dup = c.post("/api/v1/personal/watchlist", json={"symbol": "BTC"}, headers=_h())
    assert dup.status_code == 200 and dup.get_json()["symbols"] == ["BTC"]
    # remove
    rem = c.delete("/api/v1/personal/watchlist/BTC", headers=_h())
    assert rem.get_json()["symbols"] == []


def test_watchlist_capacity_enforced_409() -> None:
    app, auth, subs, wl = _app(plan="starter")
    # prefill to the limit (20)
    wl.by_account["acct"] = [f"S{i}" for i in range(20)]
    r = app.test_client().post("/api/v1/personal/watchlist", json={"symbol": "OVER"}, headers=_h())
    assert r.status_code == 409 and r.get_json()["classification"] == "CAPACITY_LIMIT_EXCEEDED"


def test_watchlist_capacity_follows_plan() -> None:
    app, auth, subs, wl = _app(plan="pro")  # watchlist_items = 50
    r = app.test_client().get("/api/v1/personal/watchlist", headers=_h())
    assert r.get_json()["capacity"] == 50


def test_watchlist_account_from_session_only() -> None:
    app, auth, subs, wl = _app(plan="starter")
    auth.sessions["sid2"] = "acct_other"
    subs.set("acct_other", "starter")
    c = app.test_client()
    c.post("/api/v1/personal/watchlist", json={"symbol": "BTC"}, headers=_h())
    # a different session sees its own (empty) list, cannot see/mutate acct's.
    other = c.get("/api/v1/personal/watchlist", headers={"X-Nexus-Session": "sid2"}).get_json()
    assert other["symbols"] == []


# --------------------------------------------------------------------------
# History downgrade
# --------------------------------------------------------------------------

def test_history_downgrade_reduces_range() -> None:
    app, auth, subs, wl = _app(plan="advanced")  # history_days = 365
    c = app.test_client()
    assert c.get("/api/v1/personal/history?days=1000", headers=_h()).get_json()["effective_days"] == 365
    subs.set("acct", "pro", STATUS_EXPIRED)  # expired -> free -> extended_market_history not entitled
    assert c.get("/api/v1/personal/history?days=1000", headers=_h()).status_code == 403


# --------------------------------------------------------------------------
# Signals / risk member-safe
# --------------------------------------------------------------------------

def test_signals_and_risk_are_member_safe_and_gated() -> None:
    app, *_ = _app(plan="pro")
    c = app.test_client()
    sig = c.get("/api/v1/personal/signals", headers=_h())
    risk = c.get("/api/v1/personal/risk", headers=_h())
    assert sig.status_code == 200 and risk.status_code == 200
    for resp in (sig, risk):
        text = resp.get_data(as_text=True).lower()
        for banned in ("order", "routing", "arm", "position_siz", "exchange_write", "provider_customer_id", "provider_subscription_id"):
            assert banned not in text
