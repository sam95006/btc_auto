"""Tests for PUB-I customer validation operations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.customer_validation.consent import record_consent
from tools.customer_validation.decision_object_concierge import record_concierge_delivery
from tools.customer_validation.evidence import (
    OBJECTION_TAXONOMY,
    paid_pilot_count,
    record_conversion_evidence,
    record_objection,
    record_wtp_evidence,
)
from tools.customer_validation.hard_bans import HARD_BANS, HardBanViolation
from tools.customer_validation.integrity import (
    REQUIRED_ZERO_COUNTERS,
    compute_counters,
    run_two_pass_integrity,
    write_two_pass_proof,
)
from tools.customer_validation.interview import (
    completed_interview_count,
    complete_interview,
    start_interview,
)
from tools.customer_validation.problem_ranking import record_problem_ranking
from tools.customer_validation.registry import enroll_participant, real_participant_count
from tools.customer_validation.store import COLLECTIONS, ensure_workspace, load_collection
from tools.customer_validation.weekly_review import record_weekly_review
from tools.customer_validation.workflow import record_workflow_map


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    return ensure_workspace(tmp_path / "cv_ws")


def test_default_workspace_counters_are_zero():
    # Package workspace must remain empty (no fabricated participants).
    pkg_ws = Path(__file__).resolve().parents[1] / "tools" / "customer_validation" / "workspace"
    ensure_workspace(pkg_ws)
    counters = compute_counters(pkg_ws)
    assert counters["real_participant_count"] == 0
    assert counters["completed_interview_count"] == 0
    assert counters["paid_pilot_count"] == 0
    assert counters["fabricated_result_count"] == 0


def test_empty_workspace_collections(ws: Path):
    for name in COLLECTIONS:
        assert load_collection(name, ws) == []


def test_refuse_fabricated_participant_ids(ws: Path):
    with pytest.raises(HardBanViolation):
        enroll_participant(
            participant_id="fake_user_1",
            enrollment_source="founder_warm_intro",
            contact_handle="real.person@domain.com",
            founder_attestation=True,
            icp_screener_passed=True,
            workspace=ws,
        )


def test_refuse_enrollment_without_founder_attestation(ws: Path):
    with pytest.raises(HardBanViolation):
        enroll_participant(
            participant_id="icp_alpha_01",
            enrollment_source="founder_warm_intro",
            contact_handle="real.person@domain.com",
            founder_attestation=False,
            icp_screener_passed=True,
            workspace=ws,
        )


def test_refuse_placeholder_contact(ws: Path):
    with pytest.raises(HardBanViolation):
        enroll_participant(
            participant_id="icp_alpha_01",
            enrollment_source="founder_warm_intro",
            contact_handle="example@example.com",
            founder_attestation=True,
            icp_screener_passed=True,
            workspace=ws,
        )


def test_refuse_interview_for_unknown_participant(ws: Path):
    with pytest.raises(HardBanViolation):
        start_interview(participant_id="nobody", workspace=ws)


def test_refuse_consent_for_unknown_participant(ws: Path):
    with pytest.raises(HardBanViolation):
        record_consent(
            participant_id="nobody",
            flags={k: True for k in (
                "scope_disclosed",
                "retention_disclosed",
                "export_rights_disclosed",
                "deletion_rights_disclosed",
                "ai_data_use_disclosed",
                "no_custody_no_trading_keys_ack",
                "participant_accepted",
            )},
            workspace=ws,
        )


def test_weekly_review_cannot_exceed_registry(ws: Path):
    with pytest.raises(HardBanViolation):
        record_weekly_review(
            week=1,
            active_participants=1,
            closed_decision_loops=0,
            thesis_completions=0,
            outcome_reviews=0,
            qualitative_notes="none",
            gate_posture="DEFER",
            operator_actions=["recruit"],
            workspace=ws,
        )


def test_wtp_refuses_live_billing(ws: Path):
    enroll_participant(
        participant_id="icp_alpha_01",
        enrollment_source="founder_warm_intro",
        contact_handle="alice@realmail.example",
        founder_attestation=True,
        icp_screener_passed=True,
        workspace=ws,
    )
    with pytest.raises(HardBanViolation):
        record_wtp_evidence(
            participant_id="icp_alpha_01",
            stated_willingness="maybe",
            package_preference="founding",
            hard_no_buy_threshold="too high",
            live_charge_attempted=True,
            workspace=ws,
        )


def test_concierge_refuses_exchange_orders(ws: Path):
    enroll_participant(
        participant_id="icp_alpha_01",
        enrollment_source="waitlist_screener",
        contact_handle="bob@realmail.example",
        founder_attestation=True,
        icp_screener_passed=True,
        workspace=ws,
    )
    fields = {
        "context_snapshot": True,
        "thesis": True,
        "evidence": True,
        "contradicting_evidence": True,
        "unknowns": True,
        "decision_or_explicit_no_action": True,
        "risk": True,
        "invalidation": True,
        "human_judgment": True,
    }
    with pytest.raises(HardBanViolation):
        record_concierge_delivery(
            participant_id="icp_alpha_01",
            decision_id="dec_001",
            fields_present=fields,
            week=1,
            exchange_order_placed=True,
            workspace=ws,
        )


def test_objection_taxonomy_cover():
    assert "want_auto_trading" in OBJECTION_TAXONOMY
    assert "decision_object_friction" in OBJECTION_TAXONOMY


def test_real_enrollment_path_updates_counters_only_when_genuine(ws: Path):
    assert real_participant_count(ws) == 0
    enroll_participant(
        participant_id="icp_alpha_01",
        enrollment_source="community_referral",
        contact_handle="carol@realmail.example",
        founder_attestation=True,
        icp_screener_passed=True,
        workspace=ws,
    )
    assert real_participant_count(ws) == 1
    start_interview(participant_id="icp_alpha_01", workspace=ws)
    assert completed_interview_count(ws) == 0
    notes = {b: f"real note for {b}" for b in (
        "current_decision_workflow",
        "where_decisions_lost",
        "invalidation_habits",
        "tool_spend_and_pain",
        "ai_trust_experiences",
        "process_vs_luck",
        "no_action_decisions",
        "stated_wtp_hypothesis_only",
        "hard_no_buy_thresholds",
        "auto_trading_demand",
    )}
    complete_interview(
        participant_id="icp_alpha_01",
        block_notes=notes,
        auto_trading_mandatory=False,
        workspace=ws,
    )
    assert completed_interview_count(ws) == 1
    record_problem_ranking(
        participant_id="icp_alpha_01",
        ranked_problems=["research_burden", "weak_invalidation"],
        workspace=ws,
    )
    record_workflow_map(
        participant_id="icp_alpha_01",
        fields={
            "tools_used": ["notion", "tradingview"],
            "decision_artifacts_today": "scattered notes",
            "research_minutes_typical_week": 300,
            "invalidation_practice": "ad hoc",
            "outcome_review_practice": "rare",
            "desired_nexus_fit": "decision loops",
        },
        workspace=ws,
    )
    record_objection(
        participant_id="icp_alpha_01",
        objection_code="decision_object_friction",
        detail="form feels long",
        workspace=ws,
    )
    record_conversion_evidence(
        participant_id="icp_alpha_01",
        conversion_type="paid_pilot",
        status="intent_only",
        workspace=ws,
    )
    assert paid_pilot_count(ws) == 0


def test_two_pass_integrity_on_empty_workspace(ws: Path):
    proof = run_two_pass_integrity(ws)
    assert proof["pass_count"] == 2
    assert proof["digests_match"] is True
    assert proof["ok"] is True
    assert proof["counters"]["real_participant_count"] == 0
    assert proof["counters"]["completed_interview_count"] == 0
    assert proof["counters"]["paid_pilot_count"] == 0
    for key in REQUIRED_ZERO_COUNTERS:
        assert proof["counters"][key] == 0


def test_two_pass_proof_file_not_status_json(ws: Path, tmp_path: Path):
    path = write_two_pass_proof(tmp_path / "proofs", ws)
    assert path.name == "customer_validation_two_pass_proof.json"
    assert not path.name.endswith("_status.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["status_json_emitted"] is False


def test_hard_bans_include_public_and_fabrication_rules():
    assert "no_fabricated_participants" in HARD_BANS
    assert "no_fabricated_interviews" in HARD_BANS
    assert "no_fabricated_paid_pilots" in HARD_BANS
    assert "no_production_customer_database" in HARD_BANS
    assert "no_live_billing" in HARD_BANS
    assert "no_automated_customer_trading" in HARD_BANS
