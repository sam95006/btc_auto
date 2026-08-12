"""V15-D Research Meta-Analysis and False Discovery tests."""
from __future__ import annotations

import pytest

from backend.nexus_research_meta_analysis import (
    ALLOWED_LABELS,
    HARD_BANS,
    HardBanViolation,
    adversarial_self_review,
    build_synthetic_experiments,
    refuse_auto_integrate,
    refuse_exchange_write,
    refuse_formal_walk_forward,
    refuse_lane_status_json,
    refuse_oos_consume,
    refuse_oos_execute,
    refuse_oos_reserve,
    refuse_promising_without_siblings,
    refuse_silent_favorable_selection,
    run_meta_analysis,
)
from backend.nexus_research_meta_analysis.bootstrap_intervals import (
    block_bootstrap_means,
    bootstrap_intervals,
    iid_bootstrap_means,
)
from backend.nexus_research_meta_analysis.correlation import (
    candidate_correlation,
    mechanism_family_correlation,
)
from backend.nexus_research_meta_analysis.duplication import detect_duplicates
from backend.nexus_research_meta_analysis.favorable_selection import (
    attempt_silent_cherry_pick,
    build_promising_packet,
    detect_favorable_run_selection,
    enforce_failed_sibling_retention,
)
from backend.nexus_research_meta_analysis.fdr import benjamini_hochberg, bonferroni_gate
from backend.nexus_research_meta_analysis.labeling import assert_label_allowed
from backend.nexus_research_meta_analysis.stability_axes import (
    capacity_sensitivity,
    combined_stability_axes,
    cost_sensitivity,
    parameter_neighborhood_stability,
    regime_stability,
    symbol_stability,
    turnover_stability,
)


def test_allowed_labels_only() -> None:
    assert "DEVELOPMENT_PROMISING_NOT_QUALIFIED" in ALLOWED_LABELS
    assert "QUALIFIED" not in ALLOWED_LABELS
    assert "PROMOTED" not in ALLOWED_LABELS
    with pytest.raises(ValueError):
        assert_label_allowed("QUALIFIED")
    with pytest.raises(ValueError):
        assert_label_allowed("WALK_FORWARD_PASS")


def test_hard_bans_document_refusals() -> None:
    assert "no_oos_consumption" in HARD_BANS
    assert "no_formal_walk_forward" in HARD_BANS
    assert "no_silent_favorable_run_selection" in HARD_BANS
    assert "no_promising_without_failed_siblings" in HARD_BANS
    assert "no_lane_status_json" in HARD_BANS
    for fn in (
        refuse_oos_consume,
        refuse_oos_execute,
        refuse_oos_reserve,
        refuse_formal_walk_forward,
        refuse_exchange_write,
        refuse_auto_integrate,
        refuse_silent_favorable_selection,
        refuse_promising_without_siblings,
        refuse_lane_status_json,
    ):
        with pytest.raises(HardBanViolation):
            fn()


def test_benjamini_hochberg_and_bonferroni() -> None:
    bh = benjamini_hochberg([0.001, 0.02, 0.8], q=0.10)
    assert bh["n_tests"] == 3
    assert 0 in bh["rejected_indices"]
    assert bh["formal_walk_forward"] is False
    assert bh["not_oos_claim"] is True
    bonf = bonferroni_gate([0.001, 0.02, 0.8], alpha=0.05)
    assert 0 in bonf["pass_indices"]


def test_bootstrap_and_block_bootstrap_deterministic() -> None:
    series = [0.01, 0.02, 0.015, 0.012, 0.018] * 10
    a = iid_bootstrap_means(series, replicates=50, seed=7)
    b = iid_bootstrap_means(series, replicates=50, seed=7)
    assert a == b
    ba = block_bootstrap_means(series, block_size=4, replicates=50, seed=7)
    bb = block_bootstrap_means(series, block_size=4, replicates=50, seed=7)
    assert ba == bb
    rep = bootstrap_intervals(series, seed=7, replicates=80)
    assert "bootstrap_intervals" in rep
    assert "block_bootstrap_intervals" in rep
    assert rep["formal_walk_forward"] is False


def test_stability_axes() -> None:
    param = parameter_neighborhood_stability(0.1, [0.09, 0.11, 0.095, 0.105])
    assert param["stable"] is True
    regime = regime_stability({"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.15})
    assert regime["stable"] is True
    symbol = symbol_stability({"X": 0.1, "Y": 0.05, "Z": 0.02})
    assert symbol["stable"] is True
    turn = turnover_stability(gross_pnl=1.0, turnover_cost=0.2)
    assert turn["stable"] is True
    cost = cost_sensitivity(
        gross_pnl=1.0, net_pnl=0.4, cost_components={"entry_fee": 0.1}
    )
    assert cost["stable"] is True
    cap = capacity_sensitivity({"a": 0.3, "b": 0.3, "c": 0.4})
    assert cap["stable"] is True


def test_correlation_and_duplication() -> None:
    experiments = build_synthetic_experiments()
    series_map = {e["experiment_id"]: e["net_series"] for e in experiments}
    cand = candidate_correlation(series_map)
    assert cand["axis"] == "candidate_correlation"
    fam = mechanism_family_correlation(experiments)
    assert fam["axis"] == "mechanism_family_correlation"
    dup = detect_duplicates(experiments)
    assert dup["duplicate_pair_count"] >= 1
    assert "EXP_DUP_001" in dup["duplicate_experiment_ids"]
    assert "EXP_DUP_002" in dup["duplicate_experiment_ids"]


def test_failed_sibling_retention_required() -> None:
    experiments = build_synthetic_experiments()
    prom = next(e for e in experiments if e["experiment_id"] == "EXP_PROM_001")
    packet = build_promising_packet(promising=prom, experiments=experiments)
    assert packet["label"] == "DEVELOPMENT_PROMISING_NOT_QUALIFIED"
    assert "EXP_PROM_FAIL_A" in packet["failed_sibling_ids"]
    assert "EXP_PROM_FAIL_B" in packet["failed_sibling_ids"]
    assert packet["qualification_claim"] is False

    with pytest.raises(HardBanViolation):
        enforce_failed_sibling_retention(
            promising_experiment_id="EXP_PROM_001",
            candidacy_group="G_PROMISING",
            experiments=experiments,
            retained_sibling_ids=["EXP_PROM_FAIL_A"],  # missing FAIL_B
        )


def test_favorable_run_selection_blocked() -> None:
    experiments = build_synthetic_experiments()
    det = detect_favorable_run_selection(
        experiments,
        attempted_silent_selection={
            "candidacy_group": "G_CHERRY",
            "selected_experiment_id": "EXP_CHERRY_FAV",
            "disclosed_member_ids": ["EXP_CHERRY_FAV"],
        },
    )
    assert det["silent_selection_blocked"] is True
    with pytest.raises(HardBanViolation):
        attempt_silent_cherry_pick(
            favorable_experiment_id="EXP_CHERRY_FAV",
            omitted_experiment_ids=["EXP_CHERRY_OMIT_A", "EXP_CHERRY_OMIT_B"],
        )


def test_run_meta_analysis_two_pass_invariants() -> None:
    report = run_meta_analysis()
    assert report["lane"] == "V15-D"
    assert report["experiment_count"] >= 10
    assert report["formal_walk_forward_executed"] is False
    assert report["oos_consumed"] is False
    assert report["oos_reserved"] is False
    assert report["qualification_ready_count"] == 0
    assert report["lane_status_json_written"] is False
    assert report["axes_coverage_ok"] is True
    assert report["deterministic_fixture_replay"] is True
    assert report["favorable_run_selection_detection"]["silent_selection_blocked"]
    assert len(report["promising_packets"]) >= 1
    for p in report["promising_packets"]:
        assert p["failed_sibling_ids"]
        assert p["qualification_claim"] is False

    adv = adversarial_self_review(report)
    assert adv["adversarial_ok"] is True
    assert adv["critical_count"] == 0
    assert adv["high_count"] == 0

    labels = {e["label"] for e in report["evaluations"]}
    assert labels <= ALLOWED_LABELS
    assert "QUALIFIED" not in labels


def test_combined_stability_on_fixture() -> None:
    experiments = build_synthetic_experiments()
    frag = next(e for e in experiments if e["experiment_id"] == "EXP_FRAG_001")
    stab = combined_stability_axes(frag)
    assert stab["regime_stability"]["stable"] is False or stab[
        "parameter_neighborhood_stability"
    ]["stable"] is False or stab["capacity_sensitivity"]["fragile"] is True
