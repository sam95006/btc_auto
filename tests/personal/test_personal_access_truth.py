"""WORKSTREAM-B trial-entitlement truth: the canonical Personal access resolver
and its consistent wiring into features, entitlement enforcement, quota policy,
and the membership (billing) display endpoints.

Covers the required matrix: active trial => Starter (entitlements + quotas),
expired trial => Free, paid wins (Starter/Pro/Advanced), Enterprise never a
Personal plan, missing created_at never fabricates Starter, view-mode spoof is
inert, and /personal/subscription == /personal/features == /billing/entitlements
== /billing/usage for the same member.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from flask import Flask

from backend.nexus_billing.routes import (
    SUBSCRIPTION_REPO_CONFIG_KEY,
    USAGE_SERVICE_CONFIG_KEY,
    register_billing_routes,
)
from backend.nexus_billing.subscription import STATUS_ACTIVE, STATUS_INACTIVE, Subscription
from backend.nexus_billing.usage_policy import quota_limit
from backend.nexus_billing.usage_service import UsageService
from backend.nexus_platform import personal_access as pa
from backend.nexus_personal.routes import (
    MARKET_SOURCE_CONFIG_KEY,
    WATCHLIST_REPO_CONFIG_KEY,
    register_personal_routes,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _sub(plan: str, status: str = STATUS_ACTIVE):
    return Subscription(account_id="acct", plan_code=plan, status=status)


# --------------------------------------------------------------------------- #
# Pure resolver (A–G).
# --------------------------------------------------------------------------- #
def test_active_trial_resolves_starter():  # A
    reg = NOW - timedelta(days=5)
    assert pa.effective_personal_plan(registered_at=reg, subscription=None, now=NOW) == "starter"
    res = pa.personal_entitlement_resolution(registered_at=reg, subscription=None, now=NOW)
    assert res.effective_plan_code == "starter"
    assert res.has("watchlists") and res.has("extended_market_history")
    assert not res.has("advanced_analysis")  # pro+
    # Starter quotas, not Free.
    assert quota_limit("starter", "watchlist_items") == 20
    assert quota_limit("starter", "history_days") == 30


def test_expired_trial_resolves_free():  # B
    reg = NOW - timedelta(days=60)
    assert pa.effective_personal_plan(registered_at=reg, subscription=None, now=NOW) == "free"
    res = pa.personal_entitlement_resolution(registered_at=reg, subscription=None, now=NOW)
    assert res.effective_plan_code == "free"
    assert not res.has("advanced_analysis")
    assert quota_limit("free", "watchlist_items") == 5


def test_paid_plans_win_over_trial():  # C, D, E
    reg = NOW - timedelta(days=60)  # trial long expired; paid must still win
    for plan in ("starter", "pro", "advanced"):
        assert pa.effective_personal_plan(registered_at=reg, subscription=_sub(plan), now=NOW) == plan
    # Pro grants advanced_analysis; Advanced grants everything up to advanced.
    pro = pa.personal_entitlement_resolution(registered_at=reg, subscription=_sub("pro"), now=NOW)
    assert pro.has("advanced_analysis") and pro.has("report_generation")


def test_enterprise_never_a_personal_plan():  # F
    reg = NOW - timedelta(days=5)
    # A (hypothetical) live enterprise billing sub must NOT resolve as Personal.
    assert pa.personal_paid_plan(_sub("enterprise")) is None
    plan = pa.effective_personal_plan(registered_at=reg, subscription=_sub("enterprise"), now=NOW)
    assert plan != "enterprise"
    assert plan == "starter"  # falls through to the active trial, never enterprise
    # And never for an expired trial either.
    assert pa.effective_personal_plan(
        registered_at=NOW - timedelta(days=60), subscription=_sub("enterprise"), now=NOW
    ) == "free"


def test_missing_created_at_no_paid_is_free_not_starter():  # G
    assert pa.effective_personal_plan(registered_at=None, subscription=None, now=NOW) == "free"
    assert pa.effective_personal_plan(registered_at="", subscription=None, now=NOW) == "free"
    # ...but a paid plan with no created_at still wins.
    assert pa.effective_personal_plan(registered_at=None, subscription=_sub("pro"), now=NOW) == "pro"


def test_billing_status_stays_truthful_during_trial():  # section 6
    reg = NOW - timedelta(days=5)
    res = pa.personal_entitlement_resolution(registered_at=reg, subscription=None, now=NOW)
    # Effective plan is Starter (product access), but the billing status is NOT
    # fabricated into a paid/active row.
    assert res.effective_plan_code == "starter"
    assert res.subscription_status == STATUS_INACTIVE


# --------------------------------------------------------------------------- #
# Route-level wiring (H, I): features == subscription == billing display, quota
# capacity follows the effective plan, view-mode spoof inert.
# --------------------------------------------------------------------------- #
class _Auth:
    def __init__(self, created_at):
        self._created = created_at

    def resolve_session(self, sid):
        return {"account_id": "acct", "created_at": self._created} if sid == "sid" else None


class _SubRepo:
    def __init__(self, sub=None):
        self._sub = sub

    def get_by_account(self, aid):
        return self._sub


class _UsageRepo:
    def __init__(self):
        self.counters = {}
        self.events = set()

    def get_used(self, account_id, quota_code, window_type, window_start):
        return self.counters.get((account_id, quota_code, window_type, window_start), 0)

    def consume(self, *, account_id, quota_code, window_type, window_start, amount, limit, idempotency_key):
        ckey = (account_id, quota_code, window_type, window_start)
        used = self.counters.get(ckey, 0)
        idem = (*ckey, idempotency_key)
        if idem in self.events:
            return True, used
        if used + amount <= limit:
            self.counters[ckey] = used + amount
            self.events.add(idem)
            return True, used + amount
        return False, used


class _WlRepo:
    def __init__(self):
        self.by_account = {}
        self._lock = threading.Lock()

    def list_symbols(self, account_id):
        return list(self.by_account.get(account_id, []))

    def try_add_symbol(self, account_id, symbol, capacity):
        with self._lock:
            items = self.by_account.setdefault(account_id, [])
            if symbol.upper() in [s.upper() for s in items]:
                return "DUPLICATE"
            if len(items) >= max(0, int(capacity)):
                return "CAPACITY"
            items.append(symbol.upper())
            return "ADDED"

    def remove_symbol(self, account_id, symbol):
        self.by_account[account_id] = [s for s in self.by_account.get(account_id, []) if s.upper() != symbol.upper()]


def _app(*, days_since_registration=None, sub=None):
    created = (
        (datetime.now(timezone.utc) - timedelta(days=days_since_registration)).isoformat()
        if days_since_registration is not None
        else None
    )
    app = Flask(__name__)
    app.config["TESTING"] = True
    subs = _SubRepo(sub)
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": _Auth(created)}
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = subs
    app.config[USAGE_SERVICE_CONFIG_KEY] = UsageService(usage_repo=_UsageRepo(), subscription_repo=subs)
    app.config[WATCHLIST_REPO_CONFIG_KEY] = _WlRepo()
    app.config[MARKET_SOURCE_CONFIG_KEY] = lambda sym: [100.0, 101.0, 103.0, 102.5, 106.0]
    register_billing_routes(app)
    register_personal_routes(app)
    return app


_H = {"X-Nexus-Session": "sid"}


def _plans_agree(client):
    sub = client.get("/api/v1/personal/subscription", headers=_H).get_json()
    feat = client.get("/api/v1/personal/features", headers=_H).get_json()
    bent = client.get("/api/v1/billing/entitlements", headers=_H).get_json()
    busage = client.get("/api/v1/billing/usage", headers=_H).get_json()
    return (
        sub["effective_plan"],
        feat["effective_plan_code"],
        bent["effective_plan_code"],
        busage["effective_plan_code"],
    )


def test_active_trial_routes_are_consistent_starter():  # I + section 3/5/7
    c = _app(days_since_registration=5).test_client()
    assert _plans_agree(c) == ("starter", "starter", "starter", "starter")
    # Capacity follows Starter (20), not Free (5); read-only.
    wl = c.get("/api/v1/personal/watchlist", headers=_H).get_json()
    assert wl["capacity"] == 20
    # Starter lacks advanced_analysis -> enforced at the backend (403), not free-gated silently.
    assert c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "k"},
                  headers=_H).status_code == 403


def test_expired_trial_routes_are_consistent_free():  # B at route level
    c = _app(days_since_registration=60).test_client()
    assert _plans_agree(c) == ("free", "free", "free", "free")
    # Free does not hold the watchlists entitlement, so the gate denies (403) —
    # proving the expired trial is genuinely Free, not silently Starter.
    assert c.get("/api/v1/personal/watchlist", headers=_H).status_code == 403


def test_paid_pro_grants_analysis_entitlement_and_quota():  # D at route level
    c = _app(days_since_registration=60, sub=_sub("pro")).test_client()
    plans = _plans_agree(c)
    assert plans == ("pro", "pro", "pro", "pro")
    # Pro holds advanced_analysis and a non-zero daily quota -> action succeeds.
    r = c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "k1"}, headers=_H)
    assert r.status_code == 200


def test_view_mode_spoof_does_not_alter_plan():  # H at route level
    c = _app(days_since_registration=5).test_client()
    spoof = {**_H, "X-Nexus-View-Mode": "advanced"}
    feat = c.get("/api/v1/personal/features?view_mode=pro&view=advanced&plan=advanced", headers=spoof).get_json()
    assert feat["effective_plan_code"] == "starter"
    sub = c.get("/api/v1/personal/subscription?view_mode=pro", headers=spoof).get_json()
    assert sub["effective_plan"] == "starter"


def test_billing_usage_watchlist_capacity_matches_personal_watchlist():  # quota consistency
    c = _app(days_since_registration=5).test_client()
    busage = c.get("/api/v1/billing/usage", headers=_H).get_json()
    wl_limit = next(q["limit"] for q in busage["quotas"] if q["quota_code"] == "watchlist_items")
    capacity = c.get("/api/v1/personal/watchlist", headers=_H).get_json()["capacity"]
    assert wl_limit == capacity == 20
