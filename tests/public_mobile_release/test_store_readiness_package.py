"""Tests for PUB-L store readiness package."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.public_mobile_release.deletion import DeletionService
from backend.public_mobile_release.entitlements import EntitlementService
from backend.public_mobile_release.ios_config_gate import validate_ios_config
from backend.public_mobile_release.android_config_gate import validate_android_config
from backend.public_mobile_release.package_gate import package_root, run_package_gate
from backend.public_mobile_release.regional_flags import RegionalFlagEngine
from backend.public_mobile_release.review_demo import activate_review_demo, assert_no_live_mixing
from backend.public_mobile_release.rollback import build_rollback_plan
from backend.public_mobile_release.two_pass import run_two_passes


def test_required_package_files_exist():
    pkg = package_root(ROOT)
    assert (pkg / "identifiers" / "app_ids.yaml").is_file()
    assert (pkg / "build" / "ios" / "PrivacyInfo.xcprivacy").is_file()
    assert (pkg / "privacy" / "data_safety_draft.md").is_file()


def test_package_gate_pass():
    findings = run_package_gate(ROOT)
    assert findings == [], [f"{f.code}:{f.path}:{f.detail}" for f in findings]


def test_two_passes_pass():
    results = run_two_passes(ROOT)
    assert all(r.ok for r in results), {
        r.name: [(f.code, f.detail) for f in r.findings] for r in results if not r.ok
    }


def test_billing_verify_hard_banned():
    svc = EntitlementService()
    result = svc.verify_purchase(
        "user-1",
        platform="ios",
        product_id="com.nexus.public.premium",
        signed_transaction="tok",
    )
    assert result.ok is False
    assert result.code == "BILLING_DISABLED"


def test_entitlement_cancel_refund_path_when_forced_active():
    svc = EntitlementService(live_billing_enabled=True, real_iap_products_enabled=True, product_allowlist={"sku"})
    # Force ACTIVE via events without store
    svc.apply_event("u", "purchase_started_or_restore")
    svc.apply_event("u", "verify_success")
    assert svc.get("u").state == "ACTIVE"
    assert svc.cancel("u").state == "CANCELED_ACTIVE_UNTIL_EXPIRY"
    svc2 = EntitlementService(live_billing_enabled=True, real_iap_products_enabled=True, product_allowlist={"sku"})
    svc2.apply_event("u2", "purchase_started_or_restore")
    svc2.apply_event("u2", "verify_success")
    assert svc2.refund("u2").state == "REFUNDED"


def test_regional_flags_force_billing_off():
    engine = RegionalFlagEngine.from_package(package_root(ROOT))
    for region in ("ZZ", "US", "EU", "TW", "CN"):
        decision = engine.evaluate(region)
        assert decision.flags.get("live_billing_enabled") is False
        assert decision.flags.get("subscription_purchase_ui") is False
        assert decision.flags.get("copy_trading") is False


def test_deletion_flow_and_private_path_ban():
    svc = DeletionService()
    req = svc.create("member-1", channel="web")
    assert req.status == "PENDING"
    svc.transition(req.request_id, "start_verify")
    svc.transition(req.request_id, "begin_purge")
    done = svc.transition(req.request_id, "complete")
    assert done.status == "COMPLETED"
    with pytest.raises(PermissionError):
        svc.create("x", path="/private/execution/wipe")
    with pytest.raises(RuntimeError):
        DeletionService(production_customer_db_enabled=True).create("x")


def test_review_demo_prod_blocked():
    session = activate_review_demo(flavor="prod", env_flag=True, deep_link_token_ok=True)
    assert session.active is False
    staging = activate_review_demo(flavor="staging", env_flag=True, deep_link_token_ok=False)
    assert staging.active is True
    assert "DEMO PREVIEW" in staging.banner
    assert assert_no_live_mixing(staging, "demo_fixture") is True
    assert staging.billing_ui == "Billing disabled"


def test_rollback_rejects_store_upload():
    plan = build_rollback_plan(["upload_to_app_store", "halt_staged_rollout"])
    assert plan.ok is False
    assert "upload_to_app_store" in plan.rejected
    assert "halt_staged_rollout" in plan.steps
    assert "disable_regional_membership_signup" in plan.steps


def test_ios_android_config_gates():
    findings, status = validate_ios_config(ROOT)
    assert findings == []
    assert status == "IOS_PROJECT_CONFIG_PASS"
    assert validate_android_config(ROOT) == []


def test_no_status_json_in_package():
    pkg = package_root(ROOT)
    assert list(pkg.rglob("*_status.json")) == []
