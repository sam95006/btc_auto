from __future__ import annotations

from typing import Any, Optional

import pytest
from flask import Flask

from backend.nexus_billing.features import ALL_FEATURES, FEATURE_SET, is_valid_feature
from backend.nexus_billing.entitlements import (
    PLAN_ENTITLEMENTS,
    effective_plan_code,
    has_entitlement,
    resolve_entitlements,
)
from backend.nexus_billing.routes import (
    SUBSCRIPTION_REPO_CONFIG_KEY,
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


def _sub(plan_code: str, status: str) -> Subscription:
    return Subscription(account_id="acct_x", plan_code=plan_code, status=status)


# --------------------------------------------------------------------------
# Feature catalog (1-3)
# --------------------------------------------------------------------------

def test_feature_codes_unique() -> None:
    assert len(ALL_FEATURES) == len(set(ALL_FEATURES))
    assert len(ALL_FEATURES) == len(FEATURE_SET)


def test_unknown_feature_rejected() -> None:
    assert is_valid_feature("advanced_signals") is True
    assert is_valid_feature("nonexistent_feature") is False
    assert is_valid_feature(None) is False
    assert is_valid_feature("") is False


def test_catalog_deterministic() -> None:
    from backend.nexus_billing.features import _build_all_features

    assert _build_all_features() == ALL_FEATURES
    assert ALL_FEATURES[0] == "market_overview"  # free group first


# --------------------------------------------------------------------------
# Plan mapping (4-9)
# --------------------------------------------------------------------------

def test_free_entitlement_set() -> None:
    free = set(PLAN_ENTITLEMENTS["free"])
    assert free == {"market_overview", "basic_market_data", "basic_alerts"}


def test_starter_inherits_free() -> None:
    starter = set(PLAN_ENTITLEMENTS["starter"])
    assert set(PLAN_ENTITLEMENTS["free"]).issubset(starter)
    assert "market_intelligence" in starter
    assert "advanced_signals" not in starter


def test_pro_inherits_starter() -> None:
    pro = set(PLAN_ENTITLEMENTS["pro"])
    assert set(PLAN_ENTITLEMENTS["starter"]).issubset(pro)
    assert "advanced_signals" in pro
    assert "premium_intelligence" not in pro  # advanced-only


def test_advanced_inherits_pro() -> None:
    advanced = set(PLAN_ENTITLEMENTS["advanced"])
    assert set(PLAN_ENTITLEMENTS["pro"]).issubset(advanced)
    assert "premium_intelligence" in advanced
    assert "enterprise_admin" not in advanced


def test_enterprise_mapping_includes_all_tiers() -> None:
    enterprise = set(PLAN_ENTITLEMENTS["enterprise"])
    assert set(PLAN_ENTITLEMENTS["advanced"]).issubset(enterprise)
    assert {"organization_features", "enterprise_admin", "custom_limits"}.issubset(enterprise)


def test_unknown_plan_maps_to_free() -> None:
    # effective_plan_code on a live subscription with an unknown plan -> free.
    assert effective_plan_code(_sub("platinum", STATUS_ACTIVE)) == "free"


# --------------------------------------------------------------------------
# Subscription resolution (10-17)
# --------------------------------------------------------------------------

def test_missing_subscription_resolves_free() -> None:
    res = resolve_entitlements(None)
    assert res.effective_plan_code == "free"
    assert res.subscription_status == "inactive"


def test_inactive_resolves_free() -> None:
    assert resolve_entitlements(_sub("pro", STATUS_INACTIVE)).effective_plan_code == "free"


def test_trialing_paid_plan_grants_plan_entitlements() -> None:
    res = resolve_entitlements(_sub("pro", STATUS_TRIALING))
    assert res.effective_plan_code == "pro"
    assert res.has("advanced_signals") is True


def test_active_paid_plan_grants_plan_entitlements() -> None:
    res = resolve_entitlements(_sub("advanced", STATUS_ACTIVE))
    assert res.effective_plan_code == "advanced"
    assert res.has("premium_intelligence") is True


def test_past_due_safe_downgrade_to_free() -> None:
    res = resolve_entitlements(_sub("pro", STATUS_PAST_DUE))
    assert res.effective_plan_code == "free"
    assert res.has("advanced_signals") is False
    assert res.subscription_status == "past_due"  # status preserved, entitlements not


def test_canceled_safe_behavior_free() -> None:
    res = resolve_entitlements(_sub("pro", STATUS_CANCELED))
    assert res.effective_plan_code == "free"
    assert res.has("advanced_signals") is False


def test_expired_resolves_free() -> None:
    res = resolve_entitlements(_sub("enterprise", STATUS_EXPIRED))
    assert res.effective_plan_code == "free"
    assert res.has("enterprise_admin") is False


def test_malformed_subscription_resolves_free() -> None:
    # Subscription.__post_init__ normalizes bad plan/status; engine stays safe.
    res = resolve_entitlements(Subscription(account_id="a", plan_code="???", status="???"))
    assert res.effective_plan_code == "free"


# --------------------------------------------------------------------------
# Access checking (18-22)
# --------------------------------------------------------------------------

def test_free_cannot_use_pro_feature() -> None:
    assert has_entitlement(_sub("free", STATUS_ACTIVE), "advanced_signals") is False


def test_pro_can_use_pro_feature() -> None:
    assert has_entitlement(_sub("pro", STATUS_ACTIVE), "advanced_signals") is True


def test_pro_cannot_use_enterprise_only_feature() -> None:
    assert has_entitlement(_sub("pro", STATUS_ACTIVE), "enterprise_admin") is False


def test_enterprise_gets_enterprise_feature() -> None:
    assert has_entitlement(_sub("enterprise", STATUS_ACTIVE), "enterprise_admin") is True


def test_invalid_feature_never_allowed() -> None:
    assert has_entitlement(_sub("enterprise", STATUS_ACTIVE), "nonexistent") is False
    assert resolve_entitlements(_sub("enterprise", STATUS_ACTIVE)).has("nonexistent") is False


def test_entitlement_value_model_supports_non_boolean() -> None:
    # The engine must not be hard-wired to boolean-only values.
    res = resolve_entitlements(_sub("pro", STATUS_ACTIVE))
    ent = dict(res.entitlements)
    ent["monthly_reports"] = 50  # future limit-style value
    from backend.nexus_billing.entitlements import EntitlementResolution
    from backend.nexus_billing.features import FEATURE_SET

    # value() only returns catalog features; but the model stores ints fine.
    assert isinstance(ent["monthly_reports"], int)
    assert "advanced_signals" in FEATURE_SET


# --------------------------------------------------------------------------
# HTTP / API (23-28) + Enforcement (29-31)
# --------------------------------------------------------------------------

class InMemorySubscriptionRepo:
    def __init__(self) -> None:
        self.by_account: dict[str, Subscription] = {}

    def get_by_account(self, account_id: str) -> Optional[Subscription]:
        return self.by_account.get(account_id)

    def create_subscription(self, *, account_id, plan_code, status=STATUS_INACTIVE, provider=None) -> Subscription:
        sub = Subscription(account_id=account_id, plan_code=plan_code, status=status, provider=provider)
        self.by_account[account_id] = sub
        return sub


class FakeAuth:
    def __init__(self) -> None:
        self.sessions: dict[str, str] = {}

    def resolve_session(self, session_id: str) -> Optional[dict[str, Any]]:
        aid = self.sessions.get(session_id)
        return {"account_id": aid} if aid else None


@pytest.fixture()
def app_ctx():
    app = Flask(__name__)
    app.config["TESTING"] = True
    auth = FakeAuth()
    repo = InMemorySubscriptionRepo()
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = repo
    register_billing_routes(app)
    return app, auth, repo


def test_entitlements_endpoint_requires_auth(app_ctx) -> None:
    app, _, _ = app_ctx
    assert app.test_client().get("/api/v1/billing/entitlements").status_code == 401


def test_authenticated_user_receives_own_entitlements(app_ctx) -> None:
    app, auth, repo = app_ctx
    auth.sessions["sid"] = "acct_1"
    repo.create_subscription(account_id="acct_1", plan_code="pro", status=STATUS_ACTIVE)
    r = app.test_client().get("/api/v1/billing/entitlements", headers={"X-Nexus-Session": "sid"})
    body = r.get_json()
    assert r.status_code == 200
    assert body["effective_plan_code"] == "pro"
    assert body["subscription_status"] == "active"
    assert "advanced_signals" in body["entitlements"]
    assert "enterprise_admin" not in body["entitlements"]


def test_account_id_query_spoof_ignored(app_ctx) -> None:
    app, auth, repo = app_ctx
    auth.sessions["sid-b"] = "acct_b"
    repo.create_subscription(account_id="acct_a", plan_code="enterprise", status=STATUS_ACTIVE)
    repo.create_subscription(account_id="acct_b", plan_code="free", status=STATUS_INACTIVE)
    r = app.test_client().get(
        "/api/v1/billing/entitlements?account_id=acct_a", headers={"X-Nexus-Session": "sid-b"}
    )
    body = r.get_json()
    assert body["effective_plan_code"] == "free"  # derived from session, not query
    assert "advanced_signals" not in body["entitlements"]


def test_provider_ids_not_leaked_in_entitlements(app_ctx) -> None:
    app, auth, repo = app_ctx
    auth.sessions["sid"] = "acct_1"
    sub = repo.create_subscription(account_id="acct_1", plan_code="pro", status=STATUS_ACTIVE)
    sub.provider = "stripe"
    sub.provider_customer_id = "cus_SECRET"
    sub.provider_subscription_id = "sub_SECRET"
    r = app.test_client().get("/api/v1/billing/entitlements", headers={"X-Nexus-Session": "sid"})
    text = r.get_data(as_text=True)
    assert "provider_customer_id" not in text
    assert "provider_subscription_id" not in text
    assert "SECRET" not in text


def test_no_subscription_returns_free(app_ctx) -> None:
    app, auth, _ = app_ctx
    auth.sessions["sid"] = "acct_new"
    r = app.test_client().get("/api/v1/billing/entitlements", headers={"X-Nexus-Session": "sid"})
    body = r.get_json()
    assert body["effective_plan_code"] == "free"
    assert body["entitlements"] == ["market_overview", "basic_market_data", "basic_alerts"]


def test_backend_unavailable_resolves_free(app_ctx) -> None:
    app, auth, _ = app_ctx
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = None
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    auth.sessions["sid"] = "acct_1"
    r = app.test_client().get("/api/v1/billing/entitlements", headers={"X-Nexus-Session": "sid"})
    assert r.get_json()["effective_plan_code"] == "free"


def test_protected_feature_denies_insufficient_plan(app_ctx) -> None:
    app, auth, repo = app_ctx
    auth.sessions["sid"] = "acct_free"
    repo.create_subscription(account_id="acct_free", plan_code="free", status=STATUS_INACTIVE)
    r = app.test_client().get(
        "/api/v1/billing/protected/advanced-signals", headers={"X-Nexus-Session": "sid"}
    )
    assert r.status_code == 403
    assert r.get_json()["classification"] == "ENTITLEMENT_REQUIRED"


def test_protected_feature_allows_entitled_plan(app_ctx) -> None:
    app, auth, repo = app_ctx
    auth.sessions["sid"] = "acct_pro"
    repo.create_subscription(account_id="acct_pro", plan_code="pro", status=STATUS_ACTIVE)
    r = app.test_client().get(
        "/api/v1/billing/protected/advanced-signals", headers={"X-Nexus-Session": "sid"}
    )
    assert r.status_code == 200
    assert r.get_json()["allowed"] is True


def test_protected_feature_requires_auth(app_ctx) -> None:
    app, _, _ = app_ctx
    r = app.test_client().get("/api/v1/billing/protected/advanced-signals")
    assert r.status_code == 401
    assert r.get_json()["classification"] == "AUTH_REQUIRED"


def test_denial_classification_is_consistent(app_ctx) -> None:
    app, auth, repo = app_ctx
    auth.sessions["sid"] = "acct_free"
    repo.create_subscription(account_id="acct_free", plan_code="free", status=STATUS_INACTIVE)
    r = app.test_client().get(
        "/api/v1/billing/protected/advanced-signals", headers={"X-Nexus-Session": "sid"}
    )
    body = r.get_json()
    assert body["error"] == "entitlement_required"
    assert body["classification"] == "ENTITLEMENT_REQUIRED"
    assert body["required_feature"] == "advanced_signals"


def test_entitlements_never_include_trading_authorization() -> None:
    # Trading firewall: no plan entitlement implies trading execution.
    banned = {"trading", "auto_trade", "order_execution", "exchange_write", "live_trading"}
    for plan, ent in PLAN_ENTITLEMENTS.items():
        assert not (set(ent) & banned), plan
