from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest
from flask import Flask

from backend.nexus_billing.routes import (
    SUBSCRIPTION_REPO_CONFIG_KEY,
    USAGE_SERVICE_CONFIG_KEY,
    register_billing_routes,
)
from backend.nexus_billing.subscription import STATUS_ACTIVE, Subscription
from backend.nexus_billing.usage_service import UsageService
from backend.nexus_personal.analysis import assess_risk
from backend.nexus_personal.market_adapter import (
    PersonalMarketAdapter,
    PersonalMarketUnavailable,
)
from backend.nexus_personal.routes import (
    MARKET_ADAPTER_CONFIG_KEY,
    WATCHLIST_REPO_CONFIG_KEY,
    register_personal_routes,
)
from backend.nexus_personal.watchlist_repository import ADD_CAPACITY, ADD_DUPLICATE, ADD_OK


# --------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------

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
    """Atomic in-memory watchlist; a Lock serializes check-then-insert like FOR UPDATE."""

    def __init__(self):
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
                return ADD_DUPLICATE
            if len(items) >= max(0, int(capacity)):
                return ADD_CAPACITY
            items.append(symbol)
            return ADD_OK

    def remove_symbol(self, account_id, symbol):
        self.by_account[account_id] = [s for s in self.by_account.get(account_id, []) if s.upper() != symbol.upper()]

    def active_watchlist_count(self, account_id):
        return 1 if self.by_account.get(account_id) else 0


class FakeHistoryService:
    """Stands in for PublicMarketHistoryService.history()."""

    def __init__(self, *, freshness="FRESH", status=200, candles=None):
        self.freshness = freshness
        self.status = status
        self.calls = []
        base_ms = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp() * 1000)
        self.candles = candles if candles is not None else [
            {"open": 100.0 + i, "high": 105.0 + i, "low": 99.0 + i, "close": 101.0 + i,
             "volume": 10.0, "close_time_ms": base_ms + i * 86_400_000}
            for i in range(130)
        ]

    def history(self, *, symbol, interval, limit):
        self.calls.append((symbol, interval, limit))
        if self.status != 200:
            return {"freshness": "UNAVAILABLE", "candles": [], "error": "provider_unavailable"}, self.status
        return (
            {
                "schema": "nexus_public_market_history_v1",
                "data_class": "LIVE_READ_ONLY",
                "provider": "binance_usdm_public",
                "symbol": symbol,
                "interval": interval,
                "freshness": self.freshness,
                "candles": self.candles[-limit:],
            },
            200,
        )


def _app(plan="pro", *, history=None, market_adapter="real", auth=True, pool=None):
    app = Flask(__name__)
    app.config["TESTING"] = True
    a = FakeAuth()
    subs = MemSubRepo()
    subs.set("acct", plan)
    usage = MemUsageRepo()
    svc = UsageService(usage_repo=usage, subscription_repo=subs,
                       clock=lambda: datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc))
    wl = MemWatchlistRepo()
    services = {}
    if auth:
        services["auth"] = a
    if pool is not None:
        services["pool"] = pool
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = services
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = subs
    app.config[USAGE_SERVICE_CONFIG_KEY] = svc
    app.config[WATCHLIST_REPO_CONFIG_KEY] = wl
    if market_adapter == "real":
        app.config[MARKET_ADAPTER_CONFIG_KEY] = PersonalMarketAdapter(history_service=history or FakeHistoryService())
    elif market_adapter is not None:
        app.config[MARKET_ADAPTER_CONFIG_KEY] = market_adapter
    register_billing_routes(app)
    register_personal_routes(app)
    a.sessions["sid"] = "acct"
    return app, a, subs, wl


def _h(sid="sid"):
    return {"X-Nexus-Session": sid}


# --------------------------------------------------------------------------
# Real market adapter
# --------------------------------------------------------------------------

def test_adapter_returns_real_series_with_provenance() -> None:
    ad = PersonalMarketAdapter(history_service=FakeHistoryService())
    series = ad.fetch_series("btcusdt")
    assert series.symbol == "BTCUSDT" and series.points >= 2
    md = series.metadata()
    assert md["provider"] == "binance_usdm_public" and md["source_class"] == "LIVE_READ_ONLY"
    assert md["freshness"] == "FRESH" and md["data_timestamp"] and md["analysis_timestamp"]


def test_adapter_unavailable_raises() -> None:
    ad = PersonalMarketAdapter(history_service=FakeHistoryService(status=503))
    with pytest.raises(PersonalMarketUnavailable):
        ad.fetch_series("BTCUSDT")
    ad2 = PersonalMarketAdapter(history_service=FakeHistoryService(freshness="UNAVAILABLE"))
    with pytest.raises(PersonalMarketUnavailable):
        ad2.fetch_series("BTCUSDT")


# --------------------------------------------------------------------------
# Analysis / report bound to real data
# --------------------------------------------------------------------------

def test_analysis_uses_real_series_and_returns_provenance() -> None:
    app, *_ = _app(plan="pro")
    r = app.test_client().post("/api/v1/personal/analysis",
                               json={"symbol": "BTCUSDT", "idempotency_key": "k1"}, headers=_h())
    body = r.get_json()
    assert r.status_code == 200 and body["analysis"]["data_class"] == "MEMBER_SAFE_ANALYSIS"
    prov = body["provenance"]
    assert prov["source_class"] == "LIVE_READ_ONLY" and prov["freshness"] == "FRESH"
    assert prov["data_timestamp"] and prov["provider"] == "binance_usdm_public"


def test_report_includes_real_provenance_and_no_secret_fields() -> None:
    app, *_ = _app(plan="pro")
    r = app.test_client().post("/api/v1/personal/report",
                               json={"symbol": "ETHUSDT", "idempotency_key": "r1"}, headers=_h())
    body = r.get_json()
    assert r.status_code == 200
    prov = body["report"]["provenance"]
    assert prov["freshness"] == "FRESH" and prov["source_class"] == "LIVE_READ_ONLY"
    text = r.get_data(as_text=True).lower()
    for banned in ("exchange_key", "order_id", "routing", "arm", "position_siz", "provider_customer_id"):
        assert banned not in text


def test_analysis_503_when_market_unavailable_no_consume() -> None:
    app, *_ = _app(plan="pro", history=FakeHistoryService(status=503))
    c = app.test_client()
    assert c.post("/api/v1/personal/analysis",
                  json={"symbol": "BTCUSDT", "idempotency_key": "k"}, headers=_h()).status_code == 503
    # Swap in a working adapter; full quota remains (nothing was consumed).
    app.config[MARKET_ADAPTER_CONFIG_KEY] = PersonalMarketAdapter(history_service=FakeHistoryService())
    r2 = c.post("/api/v1/personal/analysis", json={"symbol": "BTCUSDT", "idempotency_key": "k2"}, headers=_h())
    assert r2.get_json()["remaining"] == 99


# --------------------------------------------------------------------------
# History real bounded data + clamp
# --------------------------------------------------------------------------

def test_history_returns_real_data_clamped_to_plan() -> None:
    app, *_ = _app(plan="starter")  # history_days = 30
    r = app.test_client().get("/api/v1/personal/history?symbol=BTCUSDT&days=1000", headers=_h())
    body = r.get_json()
    assert r.status_code == 200
    assert body["effective_days"] == 30 and body["clamped"] is True
    assert body["provider_window_max"] == 120
    assert body["data_points"] == 30 and len(body["data"]) == 30  # trimmed to effective window
    assert body["source_class"] == "LIVE_READ_ONLY"


def test_history_downgrade_reduces_range() -> None:
    app, _a, subs, _wl = _app(plan="advanced")  # history_days = 365
    c = app.test_client()
    r = c.get("/api/v1/personal/history?days=1000", headers=_h()).get_json()
    assert r["effective_days"] == 365 and r["data_points"] == 120  # provider window ceiling
    from backend.nexus_billing.subscription import STATUS_EXPIRED
    subs.set("acct", "advanced", STATUS_EXPIRED)  # expired -> free -> not entitled
    assert c.get("/api/v1/personal/history?days=1000", headers=_h()).status_code == 403


def test_history_503_when_market_unavailable() -> None:
    app, *_ = _app(plan="pro", history=FakeHistoryService(status=503))
    assert app.test_client().get("/api/v1/personal/history?days=30", headers=_h()).status_code == 503


# --------------------------------------------------------------------------
# Risk integrated (member-safe) / signals unavailable
# --------------------------------------------------------------------------

def test_risk_is_member_safe_and_available_from_real_volatility() -> None:
    app, *_ = _app(plan="pro")
    r = app.test_client().get("/api/v1/personal/risk?symbol=BTCUSDT", headers=_h())
    body = r.get_json()
    assert r.status_code == 200 and body["available"] is True
    assert body["risk"]["data_class"] == "MEMBER_SAFE_RISK"
    assert body["risk"]["risk_level"] in ("contained", "moderate", "elevated")
    text = r.get_data(as_text=True).lower()
    for banned in ("position_siz", "leverage", "routing", "arm", "risk_guard", "order", "exchange_write"):
        assert banned not in text


def test_risk_503_when_unavailable() -> None:
    app, *_ = _app(plan="pro", history=FakeHistoryService(status=503))
    assert app.test_client().get("/api/v1/personal/risk", headers=_h()).status_code == 503


def test_assess_risk_is_deterministic() -> None:
    a = {"symbol": "X", "volatility": "high", "range_pct": 9.0}
    assert assess_risk(a)["risk_level"] == "elevated"
    assert assess_risk({"range_pct": 1.0})["risk_level"] == "contained"


def test_signals_explicit_unavailable_not_fabricated() -> None:
    app, *_ = _app(plan="pro")
    body = app.test_client().get("/api/v1/personal/signals", headers=_h()).get_json()
    assert body["available"] is False and body["signals"] == []
    assert body["reason"] == "no_member_safe_signal_source"


# --------------------------------------------------------------------------
# Watchlist atomic capacity + concurrency + isolation
# --------------------------------------------------------------------------

def test_watchlist_duplicate_retry_safe() -> None:
    app, *_ = _app(plan="starter")
    c = app.test_client()
    a = c.post("/api/v1/personal/watchlist", json={"symbol": "btc"}, headers=_h())
    assert a.get_json()["symbols"] == ["BTC"]
    dup = c.post("/api/v1/personal/watchlist", json={"symbol": "BTC"}, headers=_h())
    assert dup.status_code == 200 and dup.get_json()["duplicate"] is True
    assert dup.get_json()["symbols"] == ["BTC"]


def test_watchlist_capacity_409() -> None:
    app, _a, _s, wl = _app(plan="starter")  # capacity 20
    wl.by_account["acct"] = [f"S{i}" for i in range(20)]
    r = app.test_client().post("/api/v1/personal/watchlist", json={"symbol": "OVER"}, headers=_h())
    assert r.status_code == 409 and r.get_json()["classification"] == "CAPACITY_LIMIT_EXCEEDED"


def test_watchlist_concurrent_last_slot_exactly_one_wins() -> None:
    # Repository-level proof: at capacity-1, many concurrent distinct adds must
    # yield exactly one ADDED and never exceed capacity.
    wl = MemWatchlistRepo()
    capacity = 20
    wl.by_account["acct"] = [f"S{i}" for i in range(capacity - 1)]
    results: list[str] = []
    lock = threading.Lock()

    def worker(sym):
        out = wl.try_add_symbol("acct", sym, capacity)
        with lock:
            results.append(out)

    threads = [threading.Thread(target=worker, args=(f"NEW{i}",)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(ADD_OK) == 1
    assert results.count(ADD_CAPACITY) == 15
    assert wl.count("acct") == capacity  # never exceeded


def test_watchlist_concurrent_same_symbol_safe() -> None:
    wl = MemWatchlistRepo()
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker():
        out = wl.try_add_symbol("acct", "BTC", 20)
        with lock:
            outcomes.append(out)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count(ADD_OK) == 1
    assert wl.count("acct") == 1  # exactly one BTC


def test_watchlist_account_isolation() -> None:
    app, a, subs, wl = _app(plan="starter")
    a.sessions["sid2"] = "acct_other"
    subs.set("acct_other", "starter")
    c = app.test_client()
    c.post("/api/v1/personal/watchlist", json={"symbol": "BTC"}, headers=_h())
    other = c.get("/api/v1/personal/watchlist", headers=_h("sid2")).get_json()
    assert other["symbols"] == []  # cannot see acct's symbols


def test_watchlist_single_active_semantics() -> None:
    app, _a, _s, wl = _app(plan="starter")
    c = app.test_client()
    c.post("/api/v1/personal/watchlist", json={"symbol": "BTC"}, headers=_h())
    assert wl.active_watchlist_count("acct") == 1


# --------------------------------------------------------------------------
# Closed-beta health contract
# --------------------------------------------------------------------------

class _ReadyPool:
    def readiness(self):
        return {"ready": True, "reason": None}


def test_health_healthy_when_all_deps_ok() -> None:
    app, *_ = _app(plan="pro", pool=_ReadyPool())
    r = app.test_client().get("/api/v1/personal/closed-beta-health", headers=_h())
    body = r.get_json()
    assert r.status_code == 200 and body["overall"] == "healthy"
    assert body["dependencies"]["market_source"]["status"] == "ok"


def test_health_unavailable_503_when_market_unbound() -> None:
    app, *_ = _app(plan="pro", market_adapter=None, pool=_ReadyPool())
    r = app.test_client().get("/api/v1/personal/closed-beta-health", headers=_h())
    assert r.status_code == 503 and r.get_json()["overall"] == "unavailable"
    assert "market_source" in r.get_json()["critical_unavailable"]


def test_health_degraded_when_db_missing() -> None:
    app, *_ = _app(plan="pro")  # no pool
    r = app.test_client().get("/api/v1/personal/closed-beta-health", headers=_h())
    body = r.get_json()
    assert r.status_code == 200 and body["overall"] == "degraded"
    assert body["dependencies"]["database"]["status"] == "unavailable"


def test_health_unavailable_when_auth_missing() -> None:
    # auth is critical; without it the beta is not healthy.
    app = Flask(__name__)
    from backend.nexus_personal.health import closed_beta_health
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {}
    app.config[MARKET_ADAPTER_CONFIG_KEY] = PersonalMarketAdapter(history_service=FakeHistoryService())
    payload, status = closed_beta_health(app)
    assert status == 503 and "auth" in payload["critical_unavailable"]
