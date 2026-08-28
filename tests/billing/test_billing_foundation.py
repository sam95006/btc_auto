from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest
from flask import Flask

from backend.nexus_billing.plans import (
    CANONICAL_PLAN_CODES,
    DEFAULT_PLAN_CODE,
    get_plan,
    is_valid_plan_code,
    list_plans,
    normalize_plan_code,
)
from backend.nexus_billing.repository import SubscriptionRepository
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
    InvalidSubscriptionTransition,
    Subscription,
    assert_transition,
    can_transition,
    default_subscription,
)


# --------------------------------------------------------------------------
# 1-2. Plan model + stable codes
# --------------------------------------------------------------------------

def test_plan_catalog_read_and_stable_codes() -> None:
    plans = list_plans()
    codes = [p.code for p in plans]
    assert codes == ["free", "starter", "pro", "advanced", "enterprise"]
    assert CANONICAL_PLAN_CODES == ("free", "starter", "pro", "advanced", "enterprise")
    assert DEFAULT_PLAN_CODE == "free"
    pro = get_plan("PRO")  # case-insensitive lookup by stable code
    assert pro is not None and pro.code == "pro"
    # Authorization must depend on the code, not price. Price is optional metadata.
    d = pro.to_public_dict()
    assert d["code"] == "pro"
    assert "price_amount" in d  # present but not identity


def test_unknown_plan_falls_back_to_default_never_paid() -> None:
    assert is_valid_plan_code("pro") is True
    assert is_valid_plan_code("platinum") is False
    assert normalize_plan_code("platinum") == "free"
    assert normalize_plan_code(None) == "free"
    assert normalize_plan_code("") == "free"


# --------------------------------------------------------------------------
# 5-7. Serialization + transitions
# --------------------------------------------------------------------------

def test_subscription_serialization_shape() -> None:
    sub = default_subscription("acct_1")
    d = sub.to_public_dict()
    for key in (
        "account_id", "plan_code", "status", "is_live", "provider",
        "provider_customer_id", "provider_subscription_id", "started_at",
        "current_period_start", "current_period_end", "cancel_at",
        "canceled_at", "ended_at", "created_at", "updated_at",
    ):
        assert key in d
    assert d["plan_code"] == "free"
    assert d["status"] == "inactive"
    assert d["is_live"] is False


@pytest.mark.parametrize(
    "src,dst",
    [
        (STATUS_INACTIVE, STATUS_TRIALING),
        (STATUS_INACTIVE, STATUS_ACTIVE),
        (STATUS_TRIALING, STATUS_ACTIVE),
        (STATUS_TRIALING, STATUS_EXPIRED),
        (STATUS_ACTIVE, STATUS_PAST_DUE),
        (STATUS_ACTIVE, STATUS_CANCELED),
        (STATUS_PAST_DUE, STATUS_ACTIVE),
        (STATUS_CANCELED, STATUS_EXPIRED),
    ],
)
def test_valid_transitions(src, dst) -> None:
    assert can_transition(src, dst) is True
    assert_transition(src, dst)  # must not raise
    sub = Subscription(account_id="a", status=src)
    sub.transition_to(dst)
    assert sub.status == dst


@pytest.mark.parametrize(
    "src,dst",
    [
        (STATUS_INACTIVE, STATUS_PAST_DUE),
        (STATUS_EXPIRED, STATUS_ACTIVE),  # terminal
        (STATUS_CANCELED, STATUS_ACTIVE),
        (STATUS_ACTIVE, STATUS_TRIALING),
        (STATUS_ACTIVE, STATUS_ACTIVE),  # no-op is not a legal transition
        ("bogus", STATUS_ACTIVE),
        (STATUS_ACTIVE, "bogus"),
    ],
)
def test_invalid_transitions_raise(src, dst) -> None:
    assert can_transition(src, dst) is False
    with pytest.raises(InvalidSubscriptionTransition):
        assert_transition(src, dst)


def test_subscription_normalizes_bad_plan_and_status() -> None:
    sub = Subscription(account_id="a", plan_code="platinum", status="weird")
    assert sub.plan_code == "free"  # never a paid plan by accident
    assert sub.status == "inactive"


# --------------------------------------------------------------------------
# In-memory repo + HTTP routes (3,4,8,9,10)
# --------------------------------------------------------------------------

class InMemorySubscriptionRepo:
    def __init__(self) -> None:
        self.by_account: dict[str, Subscription] = {}
        self._n = 0

    def get_by_account(self, account_id: str) -> Optional[Subscription]:
        return self.by_account.get(account_id)

    def create_subscription(self, *, account_id, plan_code, status=STATUS_INACTIVE, provider=None) -> Subscription:
        sub = Subscription(account_id=account_id, plan_code=plan_code, status=status, provider=provider)
        self.by_account[account_id] = sub
        return sub

    def transition_status(self, account_id: str, to_status: str) -> Subscription:
        sub = self.by_account[account_id]
        sub.transition_to(to_status)
        return sub


class FakeAuth:
    def __init__(self) -> None:
        self.sessions: dict[str, str] = {}  # session_id -> account_id

    def resolve_session(self, session_id: str) -> Optional[dict[str, Any]]:
        aid = self.sessions.get(session_id)
        return {"account_id": aid} if aid else None


@pytest.fixture()
def billing_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    auth = FakeAuth()
    repo = InMemorySubscriptionRepo()
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = repo
    register_billing_routes(app)
    return app, auth, repo


def test_plans_endpoint_is_public(billing_app) -> None:
    app, _, _ = billing_app
    client = app.test_client()
    r = client.get("/api/v1/billing/plans")
    assert r.status_code == 200
    assert r.headers.get("Cache-Control") == "no-store"
    body = r.get_json()
    assert body["default_plan_code"] == "free"
    assert [p["code"] for p in body["plans"]] == ["free", "starter", "pro", "advanced", "enterprise"]


def test_subscription_requires_auth(billing_app) -> None:
    app, _, _ = billing_app
    r = app.test_client().get("/api/v1/billing/subscription")
    assert r.status_code == 401


def test_subscription_creation_and_authenticated_read(billing_app) -> None:
    app, auth, repo = billing_app
    auth.sessions["sid-a"] = "acct_a"
    repo.create_subscription(account_id="acct_a", plan_code="pro", status=STATUS_ACTIVE)
    r = app.test_client().get("/api/v1/billing/subscription", headers={"X-Nexus-Session": "sid-a"})
    assert r.status_code == 200
    body = r.get_json()["subscription"]
    assert body["account_id"] == "acct_a"
    assert body["plan_code"] == "pro"
    assert body["status"] == "active"
    assert body["is_live"] is True


def test_missing_subscription_resolves_to_safe_default(billing_app) -> None:
    app, auth, _ = billing_app
    auth.sessions["sid-new"] = "acct_new"  # no subscription row
    r = app.test_client().get("/api/v1/billing/subscription", headers={"X-Nexus-Session": "sid-new"})
    assert r.status_code == 200
    body = r.get_json()["subscription"]
    assert body["plan_code"] == "free"
    assert body["status"] == "inactive"
    assert body["is_live"] is False


def test_user_cannot_read_another_users_subscription(billing_app) -> None:
    app, auth, repo = billing_app
    auth.sessions["sid-a"] = "acct_a"
    auth.sessions["sid-b"] = "acct_b"
    repo.create_subscription(account_id="acct_a", plan_code="enterprise", status=STATUS_ACTIVE)
    repo.create_subscription(account_id="acct_b", plan_code="free", status=STATUS_INACTIVE)
    client = app.test_client()
    # Even if a client tries to smuggle another account id via query, it is ignored.
    r = client.get(
        "/api/v1/billing/subscription?account_id=acct_a",
        headers={"X-Nexus-Session": "sid-b"},
    )
    body = r.get_json()["subscription"]
    assert body["account_id"] == "acct_b"  # derived from session, not the query
    assert body["plan_code"] == "free"


def test_no_repo_available_fails_safe_to_default(billing_app) -> None:
    app, auth, _ = billing_app
    app.config[SUBSCRIPTION_REPO_CONFIG_KEY] = None  # simulate no persistence
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = {"auth": auth}
    auth.sessions["sid-a"] = "acct_a"
    r = app.test_client().get("/api/v1/billing/subscription", headers={"X-Nexus-Session": "sid-a"})
    body = r.get_json()["subscription"]
    assert body["plan_code"] == "free" and body["status"] == "inactive"


# --------------------------------------------------------------------------
# 11. Migration is additive and non-destructive
# --------------------------------------------------------------------------

def test_billing_migration_is_additive_and_non_destructive() -> None:
    path = Path("backend/nexus_persistence_pg/migrations/0008_billing_subscription_foundation.sql")
    sql = path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS nexus.subscriptions" in sql
    assert "REFERENCES nexus.accounts(account_id)" in sql
    upper = sql.upper()
    for destructive in ("DROP TABLE", "DROP SCHEMA", "TRUNCATE TABLE", "DELETE FROM", "ALTER TABLE"):
        assert destructive not in upper

    # The migration set still validates (versions sorted, non-destructive).
    from backend.nexus_persistence_pg import migrate

    migrations = migrate.list_migrations()
    versions = [m.version for m in migrations]
    assert "0008" in versions
    assert versions == sorted(versions)


def test_repository_uses_expected_table() -> None:
    # Guard the persistence contract without needing a live DB.
    import inspect

    src = inspect.getsource(SubscriptionRepository)
    assert "nexus.subscriptions" in src
    assert "DELETE" not in src.upper()
    assert "DROP" not in src.upper()
