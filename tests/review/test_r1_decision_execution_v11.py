"""FOUNDER R1 adversarial + authority tests (reviewer-owned).

Loads Lane A/B from sibling worktrees / git overlays; does not modify their paths.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.review.r1_decision_execution.adversarial import (
    SCENARIO_RUNNERS,
    run_adversarial_suite,
    scenario_decision_closed_position_open,
    scenario_decision_approved_twice,
    scenario_evidence_tamper_after_approval,
    scenario_intent_replay_after_restart,
    scenario_partial_fill_during_transition,
    scenario_position_closed_decision_monitoring,
    scenario_cost_model_version_mismatch,
    scenario_reopened_after_close,
    scenario_same_bar_stop_target,
)
from tools.review.r1_decision_execution.authority_scan import scan_authorities
from tools.review.r1_decision_execution.lane_loader import LaneImportContext, resolve_lane_roots
from tools.review.r1_decision_execution.runner import ARTIFACT_DIR, OWNED_PATHS, run_r1_review, write_artifacts
from tools.review.r1_decision_execution.vocabulary import analyze_vocabulary, FORBIDDEN_COMBINATIONS


@pytest.fixture(scope="module")
def roots():
    return resolve_lane_roots()


def test_owned_paths_only_policy() -> None:
    assert "tools/review/r1_decision_execution/" in OWNED_PATHS
    assert "tests/review/test_r1_decision_execution_v11.py" in OWNED_PATHS
    assert "artifacts/readiness/immutable/v11_review_decision_execution/" in OWNED_PATHS


def test_lane_roots_resolve(roots) -> None:
    assert (roots.lane_a / "backend" / "nexus_decision" / "orchestrator.py").is_file()
    assert (
        roots.lane_b / "backend" / "nexus_execution" / "microstructure_realism_v11" / "adapter.py"
    ).is_file()


def test_authority_scan_detects_bridge_and_minting(roots) -> None:
    report = scan_authorities(roots)
    ids = {c["id"] for c in report["authority_conflicts"]}
    assert "AUTH_DECISION_MINTS_INTENT_ID" in ids
    assert "AUTH_DECISION_MINTS_POSITION_ID" in ids
    assert "AUTH_NO_DECISION_EXECUTION_BRIDGE" in ids
    assert "AUTH_DECISION_RISK_BYPASS" in ids
    assert report["authority_conflict_count"] >= 4
    assert report["live"]["canonical_execution_engine_count"] == 1


def test_vocabulary_forbidden_combinations_defined(roots) -> None:
    vocab = analyze_vocabulary(roots)
    assert len(FORBIDDEN_COMBINATIONS) >= 8
    assert vocab["mismatch_count"] >= 2
    ids = {m["id"] for m in vocab["mismatches"]}
    assert "VOCAB_MONITORING_SKIP_EXIT" in ids


def test_scenario_decision_approved_twice(tmp_path, roots) -> None:
    with LaneImportContext(roots):
        from tools.review.r1_decision_execution.adversarial import _lane_a_test_names, _lane_b_test_names

        r = scenario_decision_approved_twice(
            tmp_path, roots, _lane_a_test_names(roots), _lane_b_test_names(roots)
        )
    assert r.scenario_id == "ADV_DECISION_APPROVED_TWICE"
    assert r.false_pass is True  # same-candidate dual approval
    assert r.evidence["different_key_blocked"] is True
    assert r.evidence["two_approvals_same_candidate"] is True


def test_scenario_reopened_after_close(tmp_path, roots) -> None:
    with LaneImportContext(roots):
        from tools.review.r1_decision_execution.adversarial import _lane_a_test_names, _lane_b_test_names

        r = scenario_reopened_after_close(
            tmp_path, roots, _lane_a_test_names(roots), _lane_b_test_names(roots)
        )
    assert r.observed_fail_closed is True
    assert r.false_pass is False


def test_scenario_intent_replay_after_restart(tmp_path, roots) -> None:
    with LaneImportContext(roots):
        from tools.review.r1_decision_execution.adversarial import _lane_a_test_names, _lane_b_test_names

        r = scenario_intent_replay_after_restart(
            tmp_path, roots, _lane_a_test_names(roots), _lane_b_test_names(roots)
        )
    assert r.false_pass is True
    assert r.cross_lane_invariant_enforced is False
    assert r.evidence["execution_has_matching_order_intent"] is False


def test_scenario_partial_fill_during_transition(tmp_path, roots) -> None:
    with LaneImportContext(roots):
        from tools.review.r1_decision_execution.adversarial import _lane_a_test_names, _lane_b_test_names

        r = scenario_partial_fill_during_transition(
            tmp_path, roots, _lane_a_test_names(roots), _lane_b_test_names(roots)
        )
    assert r.false_pass is True
    assert r.cross_lane_invariant_enforced is False
    assert r.evidence["decision_bound_to_exec_intent"] is False


def test_scenario_same_bar_stop_target(tmp_path, roots) -> None:
    with LaneImportContext(roots):
        from tools.review.r1_decision_execution.adversarial import _lane_a_test_names, _lane_b_test_names

        r = scenario_same_bar_stop_target(
            tmp_path, roots, _lane_a_test_names(roots), _lane_b_test_names(roots)
        )
    assert r.evidence["fill_status"] == "BLOCKED_AMBIGUOUS"
    assert r.false_pass is True  # Decision keeps monitoring


def test_scenario_cost_model_version_mismatch(tmp_path, roots) -> None:
    with LaneImportContext(roots):
        from tools.review.r1_decision_execution.adversarial import _lane_a_test_names, _lane_b_test_names

        r = scenario_cost_model_version_mismatch(
            tmp_path, roots, _lane_a_test_names(roots), _lane_b_test_names(roots)
        )
    assert r.false_pass is True
    assert r.evidence["decision_binds_cost_version"] is False
    assert len(r.evidence["divergent_versions"]) >= 1


def test_scenario_position_closed_decision_monitoring(tmp_path, roots) -> None:
    with LaneImportContext(roots):
        from tools.review.r1_decision_execution.adversarial import _lane_a_test_names, _lane_b_test_names

        r = scenario_position_closed_decision_monitoring(
            tmp_path, roots, _lane_a_test_names(roots), _lane_b_test_names(roots)
        )
    assert r.false_pass is True
    assert r.severity == "critical"


def test_scenario_decision_closed_position_open(tmp_path, roots) -> None:
    with LaneImportContext(roots):
        from tools.review.r1_decision_execution.adversarial import _lane_a_test_names, _lane_b_test_names

        r = scenario_decision_closed_position_open(
            tmp_path, roots, _lane_a_test_names(roots), _lane_b_test_names(roots)
        )
    assert r.false_pass is True
    assert r.evidence["skipped_exited"] is True
    assert r.severity == "critical"


def test_scenario_evidence_tamper_after_approval(tmp_path, roots) -> None:
    with LaneImportContext(roots):
        from tools.review.r1_decision_execution.adversarial import _lane_a_test_names, _lane_b_test_names

        r = scenario_evidence_tamper_after_approval(
            tmp_path, roots, _lane_a_test_names(roots), _lane_b_test_names(roots)
        )
    assert r.observed_fail_closed is True
    assert r.false_pass is False
    assert r.lane_a_covered is True


def test_all_required_scenarios_registered() -> None:
    ids = {fn.__name__ for fn in SCENARIO_RUNNERS}
    required = {
        "scenario_decision_approved_twice",
        "scenario_reopened_after_close",
        "scenario_intent_replay_after_restart",
        "scenario_partial_fill_during_transition",
        "scenario_same_bar_stop_target",
        "scenario_cost_model_version_mismatch",
        "scenario_position_closed_decision_monitoring",
        "scenario_decision_closed_position_open",
        "scenario_evidence_tamper_after_approval",
    }
    assert required <= ids


def test_adversarial_suite_counts(tmp_path, roots) -> None:
    suite = run_adversarial_suite(tmp_path, roots)
    assert suite["scenario_count"] == 9
    assert suite["false_PASS_count"] >= 6
    assert suite["missing_negative_test_count"] >= 6


def test_two_pass_review_and_artifacts(tmp_path, roots) -> None:
    out = tmp_path / "artifacts"
    report = run_r1_review(passes=2, tmp=tmp_path / "work")
    paths = write_artifacts(out, report=report)
    assert (out / "return_matrix.json").is_file()
    assert (out / "SUMMARY.md").is_file()
    assert (out / "BLOCKERS.json").is_file()
    matrix = json.loads((out / "return_matrix.json").read_text(encoding="utf-8"))
    assert matrix["false_PASS_count"] == report["summary"]["false_PASS_count"]
    assert matrix["authority_conflict_count"] == report["summary"]["authority_conflict_count"]
    assert matrix["missing_negative_test_count"] == report["summary"]["missing_negative_test_count"]
    assert matrix["integration_recommendation"].startswith("BLOCK_")
    assert report["summary"]["critical_count"] >= 5
    assert "pass2_confirmed_critical_ids" in report["passes"][1]
    assert paths
    # Ensure default artifact dir constant resolves under repo.
    assert ARTIFACT_DIR.name == "v11_review_decision_execution"
