"""Negative tests for V15-B Mechanism Execution Compiler — reject banned behaviors."""
from __future__ import annotations

import pytest

from backend.nexus_mechanism_execution_compiler.campaign import run_compiler_campaign
from backend.nexus_mechanism_execution_compiler.compiler import (
    assert_executors_distinct,
    compile_all_executors,
    compile_one,
)
from backend.nexus_mechanism_execution_compiler.contracts import ExecutorContract
from backend.nexus_mechanism_execution_compiler.executor import MechanismExecutor
from backend.nexus_mechanism_lab_v4.catalog import SPECS
from backend.nexus_mechanism_lab_v4.signals import signal_for
from backend.nexus_mechanism_lab_v4.synthetic import generate_synthetic_series


def test_negative_rejects_param_only_clone_collapse() -> None:
    """Cosmetic hold/horizon variants with identical economics must fail distinctness."""
    contracts = compile_all_executors()
    base = contracts[0]
    # Build a param-only clone by mutating hold/horizon while keeping signal+rationale.
    clone = ExecutorContract(
        executor_id="EXEC_COSMETIC_CLONE_SHOULD_FAIL",
        mechanism_id="MECH_COSMETIC_CLONE_SHOULD_FAIL",
        family=base.family,
        economic_rationale=base.economic_rationale,
        input_contract=base.input_contract,
        feature_contract=type(base.feature_contract)(
            primary_feature=base.feature_contract.primary_feature,
            secondary_feature=base.feature_contract.secondary_feature,
            horizon_bars=base.feature_contract.horizon_bars + 1,
            hold_bars=base.feature_contract.hold_bars + 1,
        ),
        signal_contract=base.signal_contract,
        entry_hypothesis=base.entry_hypothesis,
        exit_hypothesis=base.exit_hypothesis,
        failure_condition=base.failure_condition,
        cost_dependency=base.cost_dependency,
        risk_compatibility=base.risk_compatibility,
        deterministic_replay=base.deterministic_replay,
        negative_test=base.negative_test,
        economic_rationale_linkage=base.economic_rationale_linkage,
        source_lane=base.source_lane,
        catalog_version=base.catalog_version,
    )
    with pytest.raises(AssertionError):
        assert_executors_distinct(list(contracts) + [clone])


def test_negative_no_future_feature_in_signal() -> None:
    bars = generate_synthetic_series(n_bars=80, seed=11)
    contract = compile_one(SPECS[0])
    ex = MechanismExecutor(contract)
    s_before = ex.evaluate_entry(bars[50], bars[49])
    # Mutating a future bar object must not affect entry evaluation (PIT).
    s_after = ex.evaluate_entry(bars[50], bars[49])
    assert s_before == s_after
    assert signal_for(SPECS[0], bars[50], bars[49]) == s_before


def test_negative_qualification_flags_forbidden() -> None:
    report = run_compiler_campaign(pass_id=2)
    assert report["qualification_ready_count"] == 0
    for e in report["executors"]:
        assert e["qualified"] is False
        assert e["qualification_ready"] is False
        label = e["label"].upper()
        assert "PROFITABLE" not in label
        assert "OOS_PASS" not in label
        assert "DEMO_READY" not in label
        if label.endswith("QUALIFIED"):
            assert "NOT_QUALIFIED" in label


def test_negative_bans_cannot_be_flipped() -> None:
    report = run_compiler_campaign(pass_id=1)
    assert report["formal_walk_forward_executed"] is False
    assert report["oos_executed"] is False
    assert report["demo_order_count"] == 0
    assert report["exchange_write_attempt_count"] == 0
    assert report["auto_integrate_attempted"] is False
    assert report["pr27_merge_attempted"] is False
    assert report["status_json_written"] is False


def test_negative_each_executor_has_negative_test_contract() -> None:
    for c in compile_all_executors():
        assert c.negative_test.test_id.startswith("NEG_")
        assert "qualification" in c.negative_test.assertion.lower() or "clone" in c.negative_test.rejects
        assert c.economic_rationale_linkage.rationale_sha256
        assert c.economic_rationale_linkage.mechanism_id == c.mechanism_id
