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
from pathlib import Path

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


class _BrokenUsageRepo:
    """A usage repository whose ledger read fails — simulates a metering outage."""

    def get_used(self, *a, **k):
        raise RuntimeError("usage ledger unavailable")

    def consume(self, *a, **k):
        raise RuntimeError("usage ledger unavailable")


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


def _app(*, days_since_registration=None, sub=None, usage="ok"):
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
    if usage == "ok":
        app.config[USAGE_SERVICE_CONFIG_KEY] = UsageService(usage_repo=_UsageRepo(), subscription_repo=subs)
    elif usage == "broken":
        app.config[USAGE_SERVICE_CONFIG_KEY] = UsageService(usage_repo=_BrokenUsageRepo(), subscription_repo=subs)
    # usage == "none": leave the usage service unconfigured (no pool) -> None.
    app.config[WATCHLIST_REPO_CONFIG_KEY] = _WlRepo()
    app.config[MARKET_SOURCE_CONFIG_KEY] = lambda sym: [100.0, 101.0, 103.0, 102.5, 106.0]
    register_billing_routes(app)
    register_personal_routes(app)
    return app


_H = {"X-Nexus-Session": "sid"}


def _personal_plans_agree(client):
    """The PERSONAL access surfaces must agree (subscription / features / the
    trial-aware /personal/access endpoint) — NOT the generic /billing endpoints,
    which stay billing-only."""
    sub = client.get("/api/v1/personal/subscription", headers=_H).get_json()
    feat = client.get("/api/v1/personal/features", headers=_H).get_json()
    acc = client.get("/api/v1/personal/access", headers=_H).get_json()
    return sub["effective_plan"], feat["effective_plan_code"], acc["effective_plan_code"]


def _access_quota_limit(client, quota_code):
    acc = client.get("/api/v1/personal/access", headers=_H).get_json()
    return next(q["limit"] for q in acc["quotas"] if q["quota_code"] == quota_code)


def test_active_trial_personal_surfaces_are_starter():  # I + section 3/5
    c = _app(days_since_registration=5).test_client()
    assert _personal_plans_agree(c) == ("starter", "starter", "starter")
    # Capacity follows Starter (20), not Free (5); read-only and consistent with
    # the /personal/access quota view.
    wl = c.get("/api/v1/personal/watchlist", headers=_H).get_json()
    assert wl["capacity"] == 20 == _access_quota_limit(c, "watchlist_items")
    assert _access_quota_limit(c, "history_days") == 30
    # Starter lacks advanced_analysis -> enforced at the backend (403).
    assert c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "k"},
                  headers=_H).status_code == 403


def test_active_trial_access_tier_is_exactly_starter():  # section 8 (exact tier)
    acc = _app(days_since_registration=5).test_client().get("/api/v1/personal/access", headers=_H).get_json()
    ent = set(acc["entitlements"])
    assert {"watchlists", "extended_market_history"} <= ent          # Starter granted
    assert not ({"advanced_analysis", "report_generation"} & ent)    # Pro+ NOT granted
    assert acc["billing_status"] == "inactive"                       # raw payment truth, separate


def test_expired_trial_personal_surfaces_are_free():  # B at route level
    c = _app(days_since_registration=60).test_client()
    assert _personal_plans_agree(c) == ("free", "free", "free")
    # Free lacks the watchlists entitlement -> the gate denies (403), proving the
    # expired trial is genuinely Free, not silently Starter.
    assert c.get("/api/v1/personal/watchlist", headers=_H).status_code == 403


def test_paid_pro_grants_analysis_entitlement_and_quota():  # D at route level
    c = _app(days_since_registration=60, sub=_sub("pro")).test_client()
    assert _personal_plans_agree(c) == ("pro", "pro", "pro")
    r = c.post("/api/v1/personal/analysis", json={"symbol": "BTC", "idempotency_key": "k1"}, headers=_H)
    assert r.status_code == 200


def test_view_mode_spoof_does_not_alter_plan():  # H at route level
    c = _app(days_since_registration=5).test_client()
    spoof = {**_H, "X-Nexus-View-Mode": "advanced"}
    feat = c.get("/api/v1/personal/features?view_mode=pro&view=advanced&plan=advanced", headers=spoof).get_json()
    assert feat["effective_plan_code"] == "starter"
    acc = c.get("/api/v1/personal/access?view_mode=pro&plan=advanced", headers=spoof).get_json()
    assert acc["effective_plan_code"] == "starter"


# --------------------------------------------------------------------------- #
# Domain boundary: GENERIC BILLING must stay billing-authoritative and preserve
# Enterprise, even while the SAME account's PERSONAL access is trial-aware.
# --------------------------------------------------------------------------- #
def test_generic_billing_preserves_enterprise():  # 6A / 6B
    c = _app(days_since_registration=5, sub=_sub("enterprise")).test_client()
    bent = c.get("/api/v1/billing/entitlements", headers=_H).get_json()
    assert bent["effective_plan_code"] == "enterprise"
    assert "enterprise_admin" in bent["entitlements"]
    busage = c.get("/api/v1/billing/usage", headers=_H).get_json()
    assert busage["effective_plan_code"] == "enterprise"


def test_generic_billing_is_not_trial_aware():  # section 1/2 regression guard
    # Active trial account with NO paid billing row: generic billing stays free
    # (billing-subscription authoritative), even though PERSONAL access is Starter.
    c = _app(days_since_registration=5).test_client()
    assert c.get("/api/v1/billing/entitlements", headers=_H).get_json()["effective_plan_code"] == "free"
    assert c.get("/api/v1/personal/access", headers=_H).get_json()["effective_plan_code"] == "starter"


def test_enterprise_billing_never_becomes_personal_plan():  # 6C at route level
    c = _app(days_since_registration=5, sub=_sub("enterprise")).test_client()
    # Generic billing = enterprise; Personal access must NEVER be enterprise.
    assert c.get("/api/v1/billing/entitlements", headers=_H).get_json()["effective_plan_code"] == "enterprise"
    personal_plan = c.get("/api/v1/personal/access", headers=_H).get_json()["effective_plan_code"]
    assert personal_plan != "enterprise"
    assert personal_plan == "starter"  # falls through to the active trial


def _access(client):
    return client.get("/api/v1/personal/access", headers=_H).get_json()


def test_personal_access_usage_unavailable_when_no_service():  # section 1
    acc = _access(_app(days_since_registration=5, usage="none").test_client())
    # Plan / entitlements / billing remain correct despite usage being unavailable.
    assert acc["effective_plan_code"] == "starter"
    assert {"watchlists", "extended_market_history"} <= set(acc["entitlements"])
    assert acc["billing_status"] == "inactive"
    assert acc["usage_available"] is False and acc["quotas"] is None


def test_personal_access_usage_unavailable_on_ledger_read_error():  # section 1
    acc = _access(_app(days_since_registration=5, usage="broken").test_client())
    assert acc["effective_plan_code"] == "starter"                 # plan truth intact
    assert {"watchlists", "extended_market_history"} <= set(acc["entitlements"])
    assert acc["usage_available"] is False and acc["quotas"] is None  # not fabricated []


def test_personal_access_healthy_usage_returns_exact_quotas():  # section 1
    acc = _access(_app(days_since_registration=5, usage="ok").test_client())
    assert acc["usage_available"] is True
    q = {x["quota_code"]: x["limit"] for x in acc["quotas"]}
    assert q["watchlist_items"] == 20 and q["history_days"] == 30


def test_membership_ui_sources_effective_plan_from_personal_access():  # section 5
    billing = Path("frontend/src/member_platform_v1/pages/BillingPages.tsx").read_text(encoding="utf-8")
    auth = Path("frontend/src/member_platform_v1/context/AuthContext.tsx").read_text(encoding="utf-8")
    # Effective plan / entitlements / usage come from the trial-aware Personal
    # access endpoint, NOT the generic billing entitlement/usage endpoints.
    assert "getPersonalAccess" in billing
    assert "getBillingEntitlements" not in billing and "getBillingUsage" not in billing
    # Raw payment/subscription status still comes from billing.
    assert "getBillingSubscription" in billing
    # App-wide tier is trial-aware too (was billing-only before).
    assert "getPersonalAccess" in auth and "getBillingEntitlements" not in auth
    # Personal AuthContext tier is Personal-only: Enterprise (and unknown) fail
    # closed to free — the tier allowlist must NOT contain "enterprise".
    import re as _re
    m = _re.search(r"PERSONAL_TIERS[^\n]*=\s*\[([^\]]*)\]", auth)
    assert m is not None, "expected a PERSONAL_TIERS allowlist"
    assert "enterprise" not in m.group(1)
    for t in ("free", "starter", "pro", "advanced"):
        assert t in m.group(1)
    # No legacy member-entitlement plan fallback when Personal access fails.
    assert "getMemberEntitlements" not in auth and "mapMemberPlan" not in auth


def test_unknown_or_malformed_paid_plan_fails_closed():  # section 7
    class _FakeSub:
        is_live = True
        status = "active"

        def __init__(self, code):
            self.plan_code = code

    for bad in ("mythic", "ENTERPRISE_X", "", None, 123):
        assert pa.personal_paid_plan(_FakeSub(bad)) is None
    # A malformed effective-plan override is denied by the usage service (fail closed).
    from backend.nexus_billing.usage_service import UsageService

    svc = UsageService(usage_repo=_UsageRepo(), subscription_repo=_SubRepo(None))
    d = svc.consume(account_id="acct", quota_code="advanced_analysis_requests_daily",
                    idempotency_key="k", effective_plan="mythic")
    assert d.allowed is False and d.reason == "invalid_effective_plan"
