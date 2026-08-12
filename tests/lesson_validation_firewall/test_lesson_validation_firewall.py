"""V16-F Lesson Validation Firewall — three-pass tests.

No status JSON / report artifacts. Never marks real Lesson ACTIVE.
"""
from __future__ import annotations

import pytest

from backend.nexus_lesson_validation_firewall.bans import (
    HardBanViolation,
    active_block_reasons,
    assert_no_status_json_filenames,
    assert_required_false_flags,
    default_control_flags,
    hard_ban_probe_matrix,
    refuse_ai_self_promote,
    refuse_real_lesson_active,
    refuse_status_json_report,
)
from backend.nexus_lesson_validation_firewall.constants import (
    HARD_BANS,
    LANE,
    PROMOTION_STATES,
    SCHEMA_ID,
)
from backend.nexus_lesson_validation_firewall.firewall import (
    LessonValidationFirewall,
    run_three_pass,
    summarize_for_return,
)
from backend.nexus_lesson_validation_firewall.fixtures import (
    cherry_pick_attempt_fixture,
    synthetic_fixture_lesson,
    synthetic_real_lesson_blocked,
)
from backend.nexus_lesson_validation_firewall.gates import (
    evaluate_active_gate,
    evaluate_cherry_pick_gate,
    evaluate_transition_legality,
)
from backend.nexus_lesson_validation_firewall.guards import compare_baseline_vs_patched
from backend.nexus_lesson_validation_firewall.record import ImmutablePromotionRecordStore
from backend.nexus_lesson_validation_firewall.states import LessonPromotionStateMachine


# ---------------------------------------------------------------------------
# Pass 1 — interfaces / fixtures / pipeline
# ---------------------------------------------------------------------------


def test_promotion_pipeline_order_exact():
    assert PROMOTION_STATES == (
        "CANDIDATE",
        "REPLAY_VALIDATED",
        "WALK_FORWARD_PENDING",
        "OOS_PENDING",
        "SHADOW_PENDING",
        "DEMO_PENDING",
        "ACTIVE",
        "DEGRADED",
        "RETIRED",
    )


def test_pass1_fixture_advances_to_demo_pending_not_active():
    fw = LessonValidationFirewall()
    p1 = fw.run_pass1_interfaces_fixtures()
    assert p1["pass_ok"] is True
    assert p1["fixture_state"] == "DEMO_PENDING"
    assert p1["active_block"]["allowed"] is False
    assert p1["active_block"]["real_lesson_active"] is False
    assert p1["real_active_block"]["allowed"] is False


def test_never_mark_real_lesson_active():
    real = synthetic_real_lesson_blocked()
    gate = evaluate_active_gate(real)
    assert gate["allowed"] is False
    assert gate["real_lesson_active"] is False
    refusal = refuse_real_lesson_active(real["lesson_id"])
    assert refusal["allowed"] is False
    reasons = active_block_reasons()
    assert "V2_3_INCOMPLETE" in reasons
    assert "FORMAL_WF_FALSE" in reasons
    assert "OOS_FALSE" in reasons
    assert "LESSON_PREVENTION_BLOCKED" in reasons


def test_illegal_stage_skip_blocked():
    legality = evaluate_transition_legality("CANDIDATE", "ACTIVE")
    assert legality["allowed"] is False
    sm = LessonPromotionStateMachine(synthetic_fixture_lesson(lesson_id="T_SKIP"))
    result = sm.attempt_transition("SHADOW_PENDING", actor="founder_operator")
    assert result["allowed"] is False
    assert sm.state == "CANDIDATE"


def test_retire_from_candidate_allowed():
    sm = LessonPromotionStateMachine(synthetic_fixture_lesson(lesson_id="T_RETIRE"))
    result = sm.attempt_transition("RETIRED", actor="founder_operator")
    assert result["allowed"] is True
    assert sm.state == "RETIRED"
    assert sm.real_lesson_active is False


# ---------------------------------------------------------------------------
# Pass 2 — adversarial safety gates
# ---------------------------------------------------------------------------


def test_pass2_adversarial_gates():
    fw = LessonValidationFirewall()
    p2 = fw.run_pass2_adversarial_gates()
    assert p2["pass_ok"] is True
    assert p2["ai_promote"]["allowed"] is False
    assert p2["cherry_pick"]["allowed"] is False
    assert p2["mutation"]["allowed"] is False


def test_ai_cannot_self_promote():
    sm = LessonPromotionStateMachine(synthetic_fixture_lesson(lesson_id="T_AI"))
    result = sm.attempt_transition("REPLAY_VALIDATED", actor="ai_agent")
    assert result["allowed"] is False
    assert refuse_ai_self_promote("ai_agent")["allowed"] is False


def test_no_favorable_only_cherry_picking():
    cherry = cherry_pick_attempt_fixture()
    gate = evaluate_cherry_pick_gate(cherry)
    assert gate["allowed"] is False
    sm = LessonPromotionStateMachine(cherry)
    assert sm.attempt_transition("REPLAY_VALIDATED", actor="founder_operator")["allowed"] is False


def test_hard_ban_inventory_and_probes():
    assert "no_real_lesson_active" in HARD_BANS
    assert "no_ai_self_promote" in HARD_BANS
    assert "no_status_json_report" in HARD_BANS
    assert "no_production_mutation" in HARD_BANS
    matrix = hard_ban_probe_matrix()
    assert matrix["all_refused"] is True
    flags = assert_required_false_flags(default_control_flags())
    assert flags["ok"] is True


def test_status_json_report_banned():
    refusal = refuse_status_json_report("v16_f_status.json")
    assert refusal["allowed"] is False
    with pytest.raises(HardBanViolation):
        assert_no_status_json_filenames(["foo/v16_f_status.json"])
    with pytest.raises(HardBanViolation):
        assert_no_status_json_filenames(["foo/report.json"])


# ---------------------------------------------------------------------------
# Pass 3 — regression / immutability / false-pass harden
# ---------------------------------------------------------------------------


def test_pass3_regression_immutability():
    fw = LessonValidationFirewall()
    p3 = fw.run_pass3_regression_immutability()
    assert p3["pass_ok"] is True
    assert p3["final_active"]["allowed"] is False
    assert p3["final_active"]["real_lesson_active"] is False


def test_regression_protection_baseline_vs_patched():
    good = synthetic_fixture_lesson(lesson_id="T_REG_OK")
    assert compare_baseline_vs_patched(good)["ok"] is True
    bad = synthetic_fixture_lesson(lesson_id="T_REG_BAD")
    bad["patched_metrics"] = {"error_rate": 0.99, "repeat_error_rate": 0.9, "coverage": 0.01}
    cmp = compare_baseline_vs_patched(bad)
    assert cmp["ok"] is False
    sm = LessonPromotionStateMachine(bad)
    assert sm.attempt_transition("REPLAY_VALIDATED", actor="founder_operator")["allowed"] is False


def test_immutable_promotion_record_write_once():
    store = ImmutablePromotionRecordStore()
    first = store.append(
        {
            "record_id": "rec_test_1",
            "lesson_id": "L1",
            "from_state": "CANDIDATE",
            "to_state": "REPLAY_VALIDATED",
            "outcome": "APPLIED",
        }
    )
    assert first["allowed"] is True
    rewrite = store.attempt_rewrite("rec_test_1", {"outcome": "ACTIVE"})
    assert rewrite["allowed"] is False
    assert rewrite["unchanged"] is True
    assert store.verify_chain()["ok"] is True
    dup = store.append(
        {
            "record_id": "rec_test_1",
            "lesson_id": "L1",
            "from_state": "CANDIDATE",
            "to_state": "ACTIVE",
            "outcome": "TAMPER",
        }
    )
    assert dup["allowed"] is False


def test_force_active_still_blocked_after_full_pipeline():
    sm = LessonPromotionStateMachine(synthetic_fixture_lesson(lesson_id="T_FORCE"))
    for target in (
        "REPLAY_VALIDATED",
        "WALK_FORWARD_PENDING",
        "OOS_PENDING",
        "SHADOW_PENDING",
        "DEMO_PENDING",
    ):
        assert sm.attempt_transition(target, actor="founder_operator")["allowed"] is True
    blocked = sm.attempt_transition("ACTIVE", actor="founder_operator", force=True)
    assert blocked["allowed"] is False
    assert blocked["real_lesson_active"] is False
    assert sm.state == "DEMO_PENDING"
    assert sm.real_lesson_active is False


def test_three_pass_end_to_end_no_status_artifacts():
    result = run_three_pass()
    assert result["schema"] == SCHEMA_ID
    assert result["lane"] == LANE
    assert result["all_passes_ok"] is True
    assert result["real_lesson_active"] is False
    assert result["status_json_written"] is False
    assert result["report_written"] is False
    summary = summarize_for_return(result)
    assert summary["status"] == "PASS"
    assert summary["passes"] == {"pass1": True, "pass2": True, "pass3": True}
    assert "V2_3_INCOMPLETE" in summary["blockers"]
