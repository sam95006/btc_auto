"""PUB2-G Customer Validation Concierge App — three-pass tests.

Pass 1: usable workflow spine + empty counters
Pass 2: adversarial hard-ban / fabrication attempts
Pass 3: independent break attempts (env, status json, private imports, payload)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.nexus_customer_validation_concierge.app import create_app
from backend.nexus_customer_validation_concierge.constants import HARD_BANS, WORKFLOW_STEPS
from backend.nexus_customer_validation_concierge.hard_bans import (
    refuse_status_json_write,
    require_local_staging,
    scan_owned_sources_for_private_imports,
)
from backend.nexus_customer_validation_concierge.routes import reset_service_for_tests
from backend.nexus_customer_validation_concierge.service import ConciergeAppService
from tools.customer_validation.consent import REQUIRED_CONSENT_FLAGS
from tools.customer_validation.decision_object_concierge import DECISION_OBJECT_REQUIRED
from tools.customer_validation.hard_bans import HardBanViolation
from tools.customer_validation.integrity import (
    run_three_pass_integrity,
    write_three_pass_proof,
)
from tools.customer_validation.interview import INTERVIEW_BLOCKS
from tools.customer_validation.store import COLLECTIONS, ensure_workspace, load_collection
from tools.customer_validation.watchlist_onboarding import record_watchlist_onboarding
from tools.customer_validation.workflow_spine import (
    REQUIRED_ZERO_UNTIL_REAL,
    compute_workflow_counters,
    workflow_spine_status,
)

ROOT = Path(__file__).resolve().parents[1]
PKG_WS = ROOT / "tools" / "customer_validation" / "workspace"


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    return ensure_workspace(tmp_path / "pub2g_ws")


@pytest.fixture()
def client(ws: Path):
    os.environ["NEXUS_CONCIERGE_ENV"] = "local_staging"
    app = create_app(workspace=ws)
    app.config["TESTING"] = True
    reset_service_for_tests(ws)
    return app.test_client()


# ---------------------------------------------------------------------------
# Pass 1 — implementation / usable empty workflow
# ---------------------------------------------------------------------------


def test_pass1_package_workspace_all_counters_zero():
    ensure_workspace(PKG_WS)
    counters = compute_workflow_counters(PKG_WS)
    for key in REQUIRED_ZERO_UNTIL_REAL:
        assert counters[key] == 0, key
    assert "watchlist_onboardings" in COLLECTIONS
    assert load_collection("watchlist_onboardings", PKG_WS) == []


def test_pass1_workflow_spine_lists_all_steps(ws: Path):
    spine = workflow_spine_status(ws)
    assert spine["step_ids"] == list(WORKFLOW_STEPS)
    assert spine["all_required_zeros"] is True
    assert spine["status_json_emitted"] is False
    assert len(spine["steps"]) == 10


def test_pass1_app_meta_and_counters_endpoints(client):
    meta = client.get("/api/public/v2/concierge-validation/meta").get_json()
    assert meta["ok"] is True
    assert meta["lane"] == "PUB2-G"
    assert meta["live_billing"] is False
    assert meta["exchange_write"] is False
    counters = client.get("/api/public/v2/concierge-validation/counters").get_json()
    assert counters["all_zero"] is True
    for key, value in counters["counters"].items():
        assert value == 0, key
    spine = client.get("/api/public/v2/concierge-validation/spine").get_json()
    assert [s["step"] for s in spine["steps"]] == list(WORKFLOW_STEPS)
    ui = client.get("/concierge-validation")
    assert ui.status_code == 200
    assert b"Customer Validation Concierge" in ui.data


def test_pass1_full_workflow_only_after_real_enrollment(ws: Path):
    svc = ConciergeAppService(ws)
    assert svc.counters()["all_zero"] is True
    svc.enroll(
        {
            "participant_id": "icp_pub2g_01",
            "enrollment_source": "founder_warm_intro",
            "contact_handle": "real.founder.lead@example.org",
            "founder_attestation": True,
            "icp_screener_passed": True,
        }
    )
    flags = {k: True for k in REQUIRED_CONSENT_FLAGS}
    svc.step_consent({"participant_id": "icp_pub2g_01", "flags": flags})
    svc.step_interview_start({"participant_id": "icp_pub2g_01"})
    notes = {b: f"field note {b}" for b in INTERVIEW_BLOCKS}
    svc.step_interview_complete(
        {
            "participant_id": "icp_pub2g_01",
            "block_notes": notes,
            "auto_trading_mandatory": False,
        }
    )
    svc.step_problem_ranking(
        {
            "participant_id": "icp_pub2g_01",
            "ranked_problems": ["research_burden", "weak_invalidation"],
        }
    )
    svc.step_watchlist_onboarding(
        {
            "participant_id": "icp_pub2g_01",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "alert_preferences": {"integrity_alerts": True},
        }
    )
    fields = {k: True for k in DECISION_OBJECT_REQUIRED}
    svc.step_decision_object_delivery(
        {
            "participant_id": "icp_pub2g_01",
            "decision_id": "dec_real_001",
            "fields_present": fields,
            "week": 1,
        }
    )
    svc.step_weekly_review(
        {
            "week": 1,
            "active_participants": 1,
            "closed_decision_loops": 0,
            "thesis_completions": 0,
            "outcome_reviews": 0,
            "qualitative_notes": "first real week",
            "gate_posture": "DEFER",
            "operator_actions": ["continue_recruiting"],
        }
    )
    svc.step_retention(
        {
            "participant_id": "icp_pub2g_01",
            "day_marker": 30,
            "retained": True,
            "notes": "still active",
        }
    )
    svc.step_willingness_to_pay(
        {
            "participant_id": "icp_pub2g_01",
            "stated_willingness": "exploring",
            "package_preference": "founding",
            "hard_no_buy_threshold": "auto-trading required",
        }
    )
    svc.step_objections(
        {
            "participant_id": "icp_pub2g_01",
            "objection_code": "decision_object_friction",
            "detail": "form length",
        }
    )
    svc.step_pilot_conversion(
        {
            "participant_id": "icp_pub2g_01",
            "conversion_type": "paid_pilot",
            "status": "intent_only",
        }
    )
    counters = svc.counters()["counters"]
    assert counters["real_participant_count"] == 1
    assert counters["watchlist_onboarding_count"] == 1
    assert counters["paid_pilot_count"] == 0  # intent_only is not confirmed paid
    assert counters["fabricated_result_count"] == 0


def test_pass1_three_pass_integrity_empty(ws: Path, tmp_path: Path):
    proof = run_three_pass_integrity(ws)
    assert proof["pass_count"] == 3
    assert proof["digests_match"] is True
    assert proof["ok"] is True
    assert all(proof["counters"][k] == 0 for k in REQUIRED_ZERO_UNTIL_REAL)
    path = write_three_pass_proof(tmp_path / "proofs", ws)
    assert path.name == "customer_validation_concierge_three_pass_proof.json"
    assert not path.name.endswith("_status.json")
    assert not path.name.endswith("_report.json")


# ---------------------------------------------------------------------------
# Pass 2 — adversarial fabrication / trading / billing
# ---------------------------------------------------------------------------


def test_pass2_refuse_fabricated_participant_via_api(client):
    resp = client.post(
        "/api/public/v2/concierge-validation/enroll",
        json={
            "participant_id": "fake_user_99",
            "enrollment_source": "founder_warm_intro",
            "contact_handle": "someone@realmail.example",
            "founder_attestation": True,
            "icp_screener_passed": True,
        },
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["ok"] is False
    assert body["error"] == "hard_ban_violation"


def test_pass2_watchlist_refuses_exchange_write(ws: Path):
    ConciergeAppService(ws).enroll(
        {
            "participant_id": "icp_pub2g_02",
            "enrollment_source": "waitlist_screener",
            "contact_handle": "wl@realmail.example",
            "founder_attestation": True,
            "icp_screener_passed": True,
        }
    )
    with pytest.raises(HardBanViolation):
        record_watchlist_onboarding(
            participant_id="icp_pub2g_02",
            symbols=["BTCUSDT"],
            exchange_write_requested=True,
            workspace=ws,
        )


def test_pass2_watchlist_refuses_auto_execute_prefs(ws: Path):
    ConciergeAppService(ws).enroll(
        {
            "participant_id": "icp_pub2g_03",
            "enrollment_source": "community_referral",
            "contact_handle": "ae@realmail.example",
            "founder_attestation": True,
            "icp_screener_passed": True,
        }
    )
    with pytest.raises(HardBanViolation):
        record_watchlist_onboarding(
            participant_id="icp_pub2g_03",
            symbols=["ETHUSDT"],
            alert_preferences={"auto_execute": True},
            workspace=ws,
        )


def test_pass2_wtp_refuses_live_charge(client, ws: Path):
    reset_service_for_tests(ws)
    ConciergeAppService(ws).enroll(
        {
            "participant_id": "icp_pub2g_04",
            "enrollment_source": "founder_warm_intro",
            "contact_handle": "wtp@realmail.example",
            "founder_attestation": True,
            "icp_screener_passed": True,
        }
    )
    resp = client.post(
        "/api/public/v2/concierge-validation/steps/willingness-to-pay",
        json={
            "participant_id": "icp_pub2g_04",
            "stated_willingness": "maybe",
            "package_preference": "pro",
            "hard_no_buy_threshold": "x",
            "live_charge_attempted": True,
        },
    )
    assert resp.status_code == 403


def test_pass2_decision_delivery_refuses_exchange_order(client, ws: Path):
    reset_service_for_tests(ws)
    ConciergeAppService(ws).enroll(
        {
            "participant_id": "icp_pub2g_05",
            "enrollment_source": "founder_warm_intro",
            "contact_handle": "do@realmail.example",
            "founder_attestation": True,
            "icp_screener_passed": True,
        }
    )
    resp = client.post(
        "/api/public/v2/concierge-validation/steps/decision-object-delivery",
        json={
            "participant_id": "icp_pub2g_05",
            "decision_id": "dec_x",
            "fields_present": {k: True for k in DECISION_OBJECT_REQUIRED},
            "week": 1,
            "exchange_order_placed": True,
        },
    )
    assert resp.status_code == 403


def test_pass2_weekly_review_cannot_inflate_cohort(client, ws: Path):
    reset_service_for_tests(ws)
    resp = client.post(
        "/api/public/v2/concierge-validation/steps/weekly-review",
        json={
            "week": 1,
            "active_participants": 5,
            "closed_decision_loops": 0,
            "thesis_completions": 0,
            "outcome_reviews": 0,
            "qualitative_notes": "inflated",
            "gate_posture": "CONTINUE",
            "operator_actions": [],
        },
    )
    assert resp.status_code == 403


def test_pass2_hard_bans_cover_fabrication_and_staging():
    assert "no_fabricated_metrics" in HARD_BANS
    assert "local_staging_only" in HARD_BANS
    assert "no_private_core_exposure" in HARD_BANS


# ---------------------------------------------------------------------------
# Pass 3 — independent break attempts
# ---------------------------------------------------------------------------


def test_pass3_refuse_production_environment(monkeypatch):
    monkeypatch.setenv("NEXUS_CONCIERGE_ENV", "production")
    with pytest.raises(HardBanViolation):
        require_local_staging()


def test_pass3_refuse_live_public_deployment_flag(monkeypatch):
    monkeypatch.setenv("NEXUS_CONCIERGE_ENV", "local_staging")
    monkeypatch.setenv("NEXUS_LIVE_PUBLIC_DEPLOYMENT", "true")
    with pytest.raises(HardBanViolation):
        require_local_staging()


def test_pass3_refuse_status_and_report_json_names(tmp_path: Path):
    with pytest.raises(HardBanViolation):
        refuse_status_json_write(tmp_path / "lane_status.json")
    with pytest.raises(HardBanViolation):
        refuse_status_json_write(tmp_path / "readiness_report.json")


def test_pass3_owned_sources_have_no_private_core_imports():
    violations = scan_owned_sources_for_private_imports(ROOT)
    assert violations == []


def test_pass3_unknown_participant_steps_fail(client):
    for path, payload in (
        ("/steps/consent", {"participant_id": "ghost", "flags": {k: True for k in REQUIRED_CONSENT_FLAGS}}),
        ("/steps/watchlist-onboarding", {"participant_id": "ghost", "symbols": ["BTCUSDT"]}),
        ("/steps/objections", {"participant_id": "ghost", "objection_code": "too_expensive", "detail": "x"}),
        ("/steps/pilot-conversion", {"participant_id": "ghost", "conversion_type": "paid_pilot", "status": "intent_only"}),
    ):
        resp = client.post(f"/api/public/v2/concierge-validation{path}", json=payload)
        assert resp.status_code == 403, path


def test_pass3_three_pass_proof_stable_and_zero(ws: Path):
    a = run_three_pass_integrity(ws)
    b = run_three_pass_integrity(ws)
    assert a["ok"] and b["ok"]
    assert a["pass1_digest"] == a["pass2_digest"] == a["pass3_digest"]
    assert a["pass1_digest"] == b["pass1_digest"]
    assert a["counters"]["real_participant_count"] == 0
    assert a["counters"]["watchlist_onboarding_count"] == 0
    assert a["counters"]["paid_pilot_count"] == 0
