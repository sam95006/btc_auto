"""Adversarial Pass-2 regressions for PUB-L hard bans."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.public_mobile_release.entitlements import EntitlementService
from backend.public_mobile_release.hard_bans import scan_forbidden_substrings
from backend.public_mobile_release.package_gate import package_root
from backend.public_mobile_release.rollback import FORBIDDEN_ROLLBACK_ACTIONS, build_rollback_plan
from backend.public_mobile_release.yaml_lite import load_simple_yaml


def test_enabled_store_upload_phrase_is_detected(tmp_path: Path):
    bad = tmp_path / "evil.md"
    bad.write_text("run: upload_to_app_store\n", encoding="utf-8")
    findings = scan_forbidden_substrings(tmp_path)
    assert any(f.detail == "upload_to_app_store" for f in findings)


def test_negated_ban_docs_do_not_trip_scanner():
    findings = scan_forbidden_substrings(package_root(ROOT))
    assert findings == []


def test_product_allowlist_empty_blocks_even_if_billing_flags_true():
    svc = EntitlementService(
        live_billing_enabled=True,
        real_iap_products_enabled=True,
        product_allowlist=set(),
    )
    result = svc.verify_purchase(
        "u",
        platform="android",
        product_id="anything",
        signed_transaction="x",
    )
    assert result.code == "PRODUCT_NOT_ALLOWLISTED"


def test_restore_conflict_state():
    svc = EntitlementService(
        live_billing_enabled=True,
        real_iap_products_enabled=True,
        product_allowlist={"sku"},
    )
    result = svc.restore("u", conflict=True)
    assert result.code == "ALREADY_OWNED_OTHER_USER"
    assert result.state == "RESTORE_CONFLICT"


def test_ci_spec_denies_status_json_and_store_publish():
    ci = load_simple_yaml(package_root(ROOT) / "ci" / "pipeline_spec.yaml")
    assert ci["publish_to_stores"] is False
    arts = ci.get("artifacts") or {}
    deny = arts.get("deny") or []
    assert any("status.json" in str(x) for x in deny)
    for action in ("upload_to_app_store", "upload_to_play_store", "fastlane_deliver"):
        assert action in (ci.get("forbidden_ci_steps") or [])


def test_rollback_plan_always_verifies_hard_ban():
    plan = build_rollback_plan([])
    assert plan.steps[-1] == "verify_hard_ban_gate"
