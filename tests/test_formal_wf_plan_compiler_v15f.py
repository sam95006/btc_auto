"""Tests for V15-F Formal Walk-Forward Plan Compiler."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_formal_wf_plan.adversarial import run_two_pass_campaign
from backend.nexus_formal_wf_plan.campaign import run_campaign_and_write, write_immutable_artifacts
from backend.nexus_formal_wf_plan.compiler import (
    FormalWalkForwardPlanCompiler,
    compile_formal_wf_plan,
    compile_formal_wf_plans,
)
from backend.nexus_formal_wf_plan.constants import (
    HARD_BAN_FLAGS,
    PLAN_DIMENSIONS,
    PLAN_STATUS_READY_EXECUTION_BLOCKED,
)
from backend.nexus_formal_wf_plan.execution_gate import FormalWalkForwardExecutionGate
from backend.nexus_formal_wf_plan.fixtures import synthetic_candidate, synthetic_candidate_bundle
from backend.nexus_formal_wf_plan.hard_bans import HardBanViolation, refuse_formal_walk_forward_execution
from backend.nexus_formal_wf_plan.windows import build_fold_windows


def test_compile_plan_covers_all_dimensions():
    plan = compile_formal_wf_plan(synthetic_candidate())
    for dim in PLAN_DIMENSIONS:
        assert dim in plan
    assert plan["status"] == PLAN_STATUS_READY_EXECUTION_BLOCKED
    assert plan["formal_walk_forward_executed"] is False
    assert plan["executed"] is False
    assert plan["fold_count"] >= 1
    assert plan["parameter_freeze_rules"]["planned"] is True
    assert plan["parameter_freeze_rules"]["frozen"] is False
    assert plan["dataset_freeze"]["oos_reserved_forbidden"] is True


def test_compile_plans_never_execute():
    report = compile_formal_wf_plans(synthetic_candidate_bundle()["candidates"])
    assert report["status"] == PLAN_STATUS_READY_EXECUTION_BLOCKED
    assert report["formal_walk_forward_executed"] is False
    assert report["any_plan_executed"] is False
    assert report["all_plans_blocked"] is True
    assert report["all_dimensions_present"] is True
    assert report["execution_gate"]["all_attempts_refused"] is True
    for plan in report["plans"]:
        assert plan["formal_walk_forward_executed"] is False
        for fold in plan["folds"]:
            assert fold["formal_walk_forward_executed"] is False


def test_execution_gate_blocks():
    gate = FormalWalkForwardExecutionGate()
    plan = compile_formal_wf_plan(synthetic_candidate())
    result = gate.attempt_execute_plan(plan)
    assert result["allowed"] is False
    assert result["executed"] is False
    assert result["formal_walk_forward_executed"] is False
    with pytest.raises(HardBanViolation):
        gate.force_execute_or_raise(plan)
    with pytest.raises(HardBanViolation):
        refuse_formal_walk_forward_execution()


def test_oos_category_rejected():
    cand = synthetic_candidate()
    cand["development_interval"]["category"] = "OOS_RESERVED"
    with pytest.raises(ValueError, match="forbidden_interval_category"):
        compile_formal_wf_plan(cand)
    cand2 = synthetic_candidate()
    cand2["development_interval"]["category"] = "OOS_UNTOUCHED"
    with pytest.raises(ValueError, match="forbidden_interval_category"):
        compile_formal_wf_plan(cand2)


def test_selected_candidate_rejected():
    cand = synthetic_candidate()
    cand["selected"] = True
    with pytest.raises(ValueError, match="selected_or_promoted"):
        compile_formal_wf_plan(cand)


def test_windows_embargo_and_purge():
    as_of = 1_700_000_000_000
    windows = build_fold_windows(
        development_start_ms=as_of - 365 * 86_400_000,
        development_end_ms=as_of - 60 * 86_400_000,
    )
    assert windows["fold_count"] >= 1
    assert windows["embargo"]["embargo_days"] >= 1
    assert windows["purge_intervals"]["purge_days"] >= 1
    for fold in windows["folds"]:
        train_end = fold["training_window"]["end_ms"]
        val_start = fold["validation_window"]["start_ms"]
        assert val_start > train_end
        assert fold["embargo"]["start_ms"] == train_end + 1
        assert fold["formal_walk_forward_executed"] is False


def test_hard_ban_flags_immutable_authority():
    for k, v in HARD_BAN_FLAGS.items():
        if k.endswith("_count"):
            assert v == 0
        else:
            assert v is False


def test_two_pass_campaign_ok():
    result = run_two_pass_campaign()
    assert result["status"] == PLAN_STATUS_READY_EXECUTION_BLOCKED
    assert result["formal_walk_forward_executed"] is False
    assert result["both_passes_ok"] is True
    assert result["pass2"]["adversarial_ok"] is True
    assert result["pass2"]["force_execute"]["executed"] is False
    assert result["pass2"]["tamper_detected"] is True
    assert result["pass2"]["oos_injection_blocked"] is True
    assert result["pass2"]["select_blocked"] is True


def test_artifacts_exclude_status_json(tmp_path: Path):
    two = run_two_pass_campaign()
    written = write_immutable_artifacts(two, root=tmp_path, lane_head="TEST")
    art = tmp_path / "artifacts" / "readiness" / "immutable" / "v15_formal_wf_plan"
    assert art.is_dir()
    assert list(art.glob("*_status.json")) == []
    summary = json.loads((art / "campaign_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == PLAN_STATUS_READY_EXECUTION_BLOCKED
    assert summary["formal_walk_forward_executed"] is False
    assert "summary" in written


def test_compiler_facade_and_campaign(tmp_path: Path):
    comp = FormalWalkForwardPlanCompiler(code_version="TESTCODE")
    report = comp.compile_bundle()
    assert report["formal_walk_forward_executed"] is False
    attempt = comp.attempt_execute(report["plans"][0])
    assert attempt["allowed"] is False
    out = run_campaign_and_write(root=tmp_path, lane_head="TEST")
    assert out["both_passes_ok"] is True
    assert out["formal_walk_forward_executed"] is False
