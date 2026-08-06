"""PUB17-D security tests — subscription product boundary."""
from __future__ import annotations

import pytest

from backend.nexus_public_subscription_boundary.audit import SubscriptionAuditLog
from backend.nexus_public_subscription_boundary.authorization import (
    assert_member_cannot_buy_forbidden,
    authorize_member_product_access,
)
from backend.nexus_public_subscription_boundary.constants import (
    MEMBER_BUYABLE_PRODUCT_IDS,
    MEMBER_FORBIDDEN_PRODUCT_IDS,
)
from backend.nexus_public_subscription_boundary.dto import build_catalog_dto
from backend.nexus_public_subscription_boundary.entitlements import (
    grant_product_manual,
    has_product,
    products_for_tier,
)
from backend.nexus_public_subscription_boundary.execution_control import (
    count_member_execution_controls,
)
from backend.nexus_public_subscription_boundary.hard_bans import HardBanViolation
from backend.nexus_public_subscription_boundary.nav import (
    FORBIDDEN_WEB_NAV_PATHS,
    assert_mobile_nav_clean,
    assert_web_nav_clean,
)
from backend.nexus_public_subscription_boundary.service import SubscriptionBoundaryService


def test_buyable_catalog_excludes_forbidden():
    catalog = build_catalog_dto().to_dict()
    buyable_ids = {p["product_id"] for p in catalog["buyable"]}
    assert buyable_ids == set(MEMBER_BUYABLE_PRODUCT_IDS)
    assert buyable_ids.isdisjoint(MEMBER_FORBIDDEN_PRODUCT_IDS)
    assert catalog["member_execution_control_count"] == 0


def test_forbidden_products_not_buyable():
    for pid in MEMBER_FORBIDDEN_PRODUCT_IDS:
        with pytest.raises(HardBanViolation):
            authorize_member_product_access(
                account_id="acct_1", product_id=pid, action="buy"
            )


def test_buyable_products_authorize_without_billing():
    result = authorize_member_product_access(
        account_id="acct_1", product_id="market_data", action="buy"
    )
    assert result["authorized"] is True
    assert result["live_billing"] is False
    assert result["execution_controls"] is False


def test_assert_member_cannot_buy_forbidden():
    out = assert_member_cannot_buy_forbidden()
    assert out["ok"] is True
    assert set(out["denied_products"]) == set(MEMBER_FORBIDDEN_PRODUCT_IDS)


def test_tier_entitlements_never_grant_forbidden():
    for tier in ("Free", "Pro", "Elite", "Enterprise"):
        products = products_for_tier(tier)
        assert products.isdisjoint(MEMBER_FORBIDDEN_PRODUCT_IDS)
        for pid in MEMBER_FORBIDDEN_PRODUCT_IDS:
            with pytest.raises(HardBanViolation):
                has_product(tier, pid)


def test_grant_forbidden_refused():
    with pytest.raises(HardBanViolation):
        grant_product_manual(
            tier="Enterprise", product_id="auto_trading", actor="manual_operator"
        )


def test_audit_denies_forbidden_and_count_stays_zero():
    audit = SubscriptionAuditLog()
    svc = SubscriptionBoundaryService(audit=audit)
    with pytest.raises(HardBanViolation):
        svc.authorize(account_id="acct_x", product_id="copy_trading", action="buy")
    events = audit.list_events()
    assert any(e["result"] == "denied" for e in events)
    assert audit.granted_execution_control_count() == 0
    scan = svc.execution_control_count()
    assert scan["member_execution_control_count"] == 0
    assert scan["status"] == "PASS"


def test_web_nav_rejects_forbidden_paths():
    assert_web_nav_clean(["/home", "/market", "/alerts"])
    for path in FORBIDDEN_WEB_NAV_PATHS:
        with pytest.raises(HardBanViolation):
            assert_web_nav_clean([path])


def test_mobile_nav_rejects_forbidden_routes():
    assert_mobile_nav_clean(["/", "/markets", "/alerts", "/membership"])
    with pytest.raises(HardBanViolation):
        assert_mobile_nav_clean(["/auto-trading"])


def test_member_execution_control_count_is_zero():
    scan = count_member_execution_controls(
        buyable_catalog=MEMBER_BUYABLE_PRODUCT_IDS,
        entitled_products=MEMBER_BUYABLE_PRODUCT_IDS,
        nav_destinations=["home", "market_data", "alerts", "ai_intelligence"],
        audit_granted_products=["market_data"],
    )
    assert scan["member_execution_control_count"] == 0
    assert scan["survivors"] == []


def test_member_execution_control_count_detects_smuggle():
    scan = count_member_execution_controls(
        buyable_catalog=["market_data", "auto_trading"],
    )
    assert scan["member_execution_control_count"] >= 1
    assert scan["status"] == "FAIL"


def test_foundation_status_reports_zero_execution_controls():
    svc = SubscriptionBoundaryService(audit=SubscriptionAuditLog())
    status = svc.foundation_status()
    assert status["member_execution_control_count"] == 0
    assert status["live_billing_enabled"] is False
    assert status["pr26_merged"] is False
    assert status["pr27_merged"] is False
    assert set(status["member_forbidden_products"]) == set(MEMBER_FORBIDDEN_PRODUCT_IDS)


def test_auth_denylist_includes_pub17_products():
    from backend.nexus_public_auth.constants import PRIVATE_EXECUTION_FEATURE_DENYLIST
    from backend.nexus_public_auth.entitlements import assert_not_private_execution_feature

    for pid in MEMBER_FORBIDDEN_PRODUCT_IDS:
        assert pid in PRIVATE_EXECUTION_FEATURE_DENYLIST
        with pytest.raises(Exception):
            assert_not_private_execution_feature(pid)


def test_flask_routes_refuse_forbidden_buy():
    flask = pytest.importorskip("flask")
    from backend.nexus_public_subscription_boundary.routes import (
        create_subscription_boundary_blueprint,
    )

    app = flask.Flask(__name__)
    app.register_blueprint(
        create_subscription_boundary_blueprint(SubscriptionBoundaryService(SubscriptionAuditLog()))
    )
    client = app.test_client()
    denied = client.post(
        "/api/public/subscription/buy/auto_trading",
        json={"account_id": "acct_1"},
    )
    assert denied.status_code == 403
    body = denied.get_json()
    assert body["hard_ban"] is True
    assert body["member_execution_control_count"] == 0

    catalog = client.get("/api/public/subscription/catalog")
    assert catalog.status_code == 200
    assert catalog.get_json()["catalog"]["member_execution_control_count"] == 0

    count = client.get("/api/public/subscription/execution-control-count")
    assert count.status_code == 200
    assert count.get_json()["member_execution_control_count"] == 0
