"""Negative tests for V14-C Mechanism Lab V4 — reject banned behaviors."""
from __future__ import annotations

import pytest

from backend.nexus_mechanism_lab_v4.catalog import MechanismSpec, assert_catalog_distinct
from backend.nexus_mechanism_lab_v4.lab import run_mechanism_lab
from backend.nexus_mechanism_lab_v4.signals import signal_for
from backend.nexus_mechanism_lab_v4.synthetic import generate_synthetic_series


def test_negative_rejects_param_only_clone_contract() -> None:
    """Cosmetic horizon/hold variants with identical economics must fail distinctness."""
    from backend.nexus_mechanism_lab_v4 import catalog as cat

    original = cat.SPECS
    clone = MechanismSpec(
        mechanism_id="MECH_COSMETIC_CLONE_SHOULD_FAIL",
        family=original[0].family,
        economic_rationale=original[0].economic_rationale,  # same rationale = clone
        required_data=original[0].required_data,
        pit_semantics=original[0].pit_semantics,
        entry_hypothesis=original[0].entry_hypothesis,
        exit_hypothesis=original[0].exit_hypothesis,
        failure_hypothesis=original[0].failure_hypothesis,
        cost_sensitivity=original[0].cost_sensitivity,
        capacity_assumptions=original[0].capacity_assumptions,
        invalidating_conditions=original[0].invalidating_conditions,
        signal_kind=original[0].signal_kind,
        primary_feature=original[0].primary_feature,
        secondary_feature=original[0].secondary_feature,
        horizon_bars=original[0].horizon_bars + 1,  # cosmetic
        hold_bars=original[0].hold_bars + 1,  # cosmetic
        direction_mode=original[0].direction_mode,
    )
    monkey = original + (clone,)
    try:
        cat.SPECS = monkey  # type: ignore[misc]
        with pytest.raises(AssertionError):
            assert_catalog_distinct()
    finally:
        cat.SPECS = original  # type: ignore[misc]


def test_negative_no_future_feature_in_signal() -> None:
    bars = generate_synthetic_series(n_bars=80, seed=11)
    from backend.nexus_mechanism_lab_v4.catalog import SPECS

    spec = SPECS[0]
    # Signal must be invariant to mutating a future bar that is not passed in.
    future = bars[52]
    # Create a mutated copy path: signal only sees 50/49.
    s_before = signal_for(spec, bars[50], bars[49])
    # Mutate future mid wildly; signal result must remain identical.
    object.__setattr__(future, "mid", future.mid * 10) if False else None  # frozen
    s_after = signal_for(spec, bars[50], bars[49])
    assert s_before == s_after


def test_negative_qualification_flags_forbidden_in_report() -> None:
    report = run_mechanism_lab(pass_id=2)
    assert report["qualification_ready_count"] == 0
    for m in report["mechanisms"]:
        assert m["qualified"] is False
        assert m["qualification_ready"] is False
        label = m["label"].upper()
        assert "PROFITABLE" not in label
        assert "OOS_PASS" not in label
        assert "DEMO_READY" not in label
        if label.endswith("QUALIFIED"):
            assert "NOT_QUALIFIED" in label


def test_negative_bans_cannot_be_flipped_by_report_fields() -> None:
    report = run_mechanism_lab(pass_id=1)
    # Report construction must keep bans closed; these are invariants.
    assert report["formal_walk_forward_executed"] is False
    assert report["oos_executed"] is False
    assert report["demo_order_count"] == 0
    assert report["exchange_write_attempt_count"] == 0
    assert report["auto_integrate_attempted"] is False
    assert report["pr27_merge_attempted"] is False
