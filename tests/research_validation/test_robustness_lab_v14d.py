"""V14-D Robustness and Multiple-Testing Lab tests."""
from __future__ import annotations

import pytest

from backend.nexus_research_validation import (
    ALLOWED_LABELS,
    HARD_BANS,
    HardBanViolation,
    adversarial_self_review,
    build_synthetic_candidates,
    refuse_auto_integrate,
    refuse_exchange_write,
    refuse_formal_walk_forward,
    refuse_oos_consume,
    run_robustness_lab,
)
from backend.nexus_research_validation.bootstrap import (
    block_bootstrap_means,
    bootstrap_stability_report,
    iid_bootstrap_means,
)
from backend.nexus_research_validation.clustering import cluster_candidates
from backend.nexus_research_validation.cost_turnover import cost_turnover_sensitivity
from backend.nexus_research_validation.fdr import (
    benjamini_hochberg,
    bonferroni_gate,
    multiple_testing_reject_decision,
)
from backend.nexus_research_validation.labeling import assert_label_allowed, assign_label
from backend.nexus_research_validation.lineage import build_lineage, lineage_index
from backend.nexus_research_validation.metadata import multiple_comparison_metadata
from backend.nexus_research_validation.sample_size import sample_size_requirements
from backend.nexus_research_validation.stability import (
    combined_stability_report,
    parameter_neighborhood_stability,
    regime_stability,
    symbol_stability,
)
from backend.nexus_research_validation.ts_dependence import (
    effective_sample_size,
    ts_dependence_controls,
)


def test_allowed_labels_only() -> None:
    assert "DEVELOPMENT_ROBUST" in ALLOWED_LABELS
    assert "QUALIFIED" not in ALLOWED_LABELS
    assert "PROMOTED" not in ALLOWED_LABELS
    with pytest.raises(ValueError):
        assert_label_allowed("QUALIFIED")
    with pytest.raises(ValueError):
        assert_label_allowed("WALK_FORWARD_PASS")


def test_hard_bans_document_refusals() -> None:
    assert "no_oos_consumption" in HARD_BANS
    assert "no_formal_walk_forward" in HARD_BANS
    assert "no_auto_integrate" in HARD_BANS
    for fn in (
        refuse_oos_consume,
        refuse_formal_walk_forward,
        refuse_exchange_write,
        refuse_auto_integrate,
    ):
        with pytest.raises(HardBanViolation):
            fn()


def test_benjamini_hochberg_discovers_strong_signals() -> None:
    bh = benjamini_hochberg([0.001, 0.02, 0.8], q=0.10)
    assert bh["n_tests"] == 3
    assert 0 in bh["rejected_indices"]
    assert bh["formal_walk_forward"] is False
    assert bh["not_oos_claim"] is True
    bonf = bonferroni_gate([0.001, 0.02, 0.8], alpha=0.05)
    assert 0 in bonf["pass_indices"]


def test_multiple_testing_reject_decision() -> None:
    assert multiple_testing_reject_decision(0.5, bh_adjusted_p=0.6, family_test_count=10)
    assert not multiple_testing_reject_decision(
        0.01, bh_adjusted_p=0.05, family_test_count=10
    )


def test_bootstrap_and_block_bootstrap_deterministic() -> None:
    series = [0.01, 0.02, 0.015, 0.012, 0.018] * 10
    a = iid_bootstrap_means(series, replicates=50, seed=7)
    b = iid_bootstrap_means(series, replicates=50, seed=7)
    assert a == b
    ba = block_bootstrap_means(series, block_size=4, replicates=50, seed=7)
    bb = block_bootstrap_means(series, block_size=4, replicates=50, seed=7)
    assert ba == bb
    rep = bootstrap_stability_report(series, seed=7, replicates=80)
    assert "iid_bootstrap" in rep
    assert "block_bootstrap" in rep
    assert rep["formal_walk_forward"] is False


def test_ts_dependence_effective_sample() -> None:
    independent = [((-1) ** i) * 0.01 for i in range(60)]
    ess = effective_sample_size(independent)
    assert ess["n"] == 60
    assert ess["n_eff"] >= 24
    dependent = []
    x = 0.0
    for _ in range(60):
        x = 0.9 * x + 0.01
        dependent.append(x)
    ts = ts_dependence_controls(dependent)
    assert "acf_profile" in ts
    assert ts["formal_walk_forward"] is False


def test_stability_axes() -> None:
    param = parameter_neighborhood_stability(0.1, [0.09, 0.11, 0.095, 0.105])
    assert param["stable"] is True
    regime = regime_stability(
        {"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.15}
    )
    assert regime["stable"] is True
    concentrated = regime_stability({"A": 1.0, "B": 0.01})
    assert concentrated["stable"] is False
    symbols = symbol_stability({"X": 0.1, "Y": 0.1, "Z": 0.05, "W": -0.01})
    assert symbols["stable"] is True
    combined = combined_stability_report(
        base_metric=0.1,
        neighbor_metrics=[0.09, 0.11, 0.1],
        regime_net={"A": 0.2, "B": 0.2, "C": 0.15},
        symbol_net={"X": 0.1, "Y": 0.1, "Z": 0.05},
    )
    assert combined["all_stability_axes_ok"] is True


def test_sample_size_gate() -> None:
    ok = sample_size_requirements(n_observations=50, n_trades=20, n_eff=30.0)
    assert ok["sufficient"] is True
    bad = sample_size_requirements(n_observations=10, n_trades=5, n_eff=5.0)
    assert bad["sufficient"] is False
    assert "OBSERVATIONS_BELOW_MIN" in bad["blockers"]


def test_cost_turnover_destruction() -> None:
    comps = {
        "entry_fee": 0.1,
        "exit_fee": 0.1,
        "spread_cost": 0.1,
        "slippage_cost": 0.1,
        "funding_cost": 0.1,
        "partial_fill_cost": 0.1,
        "cancel_replace_cost": 0.1,
        "market_impact_approximation": 0.1,
        "turnover_cost": 0.5,
    }
    destroyed = cost_turnover_sensitivity(
        gross_pnl=0.5,
        net_pnl=-0.2,
        cost_components=comps,
        turnover_notional=100.0,
    )
    assert destroyed["destroyed"] is True
    assert destroyed["cost_destroyed"] is True


def test_correlation_clustering_finds_twins() -> None:
    base = [0.01 + (i % 5) * 0.001 for i in range(40)]
    twin = [x + 0.0001 for x in base]
    other = [((-1) ** i) * 0.02 for i in range(40)]
    out = cluster_candidates(
        {"A": base, "B": twin, "C": other},
        threshold=0.80,
    )
    assert out["cluster_count"] >= 2
    assert any(
        set(c["members"]) >= {"A", "B"} or {"A", "B"} <= set(c["members"])
        for c in out["clusters"]
    )


def test_lineage_and_metadata() -> None:
    lin = build_lineage(
        candidate_id="C1",
        research_family="ORDER_FLOW_IMBALANCE",
        mechanism_semantic_id="M1",
        parent_experiment_id=None,
        parameter_checksum="abc",
        feature_version="F1",
        universe_checksum="U1",
        data_fixture_id="FIX1",
        random_seed=1,
    )
    assert lin["oos_consumed"] is False
    assert lin["lineage_digest"]
    idx = lineage_index([lin])
    assert idx["candidate_count"] == 1
    meta = multiple_comparison_metadata(
        family_id="ORDER_FLOW_IMBALANCE",
        candidate_ids=["C1", "C2"],
        p_values=[0.01, 0.4],
    )
    assert meta["n_tests"] == 2
    assert meta["qualification_claim"] is False


def test_assign_label_priority() -> None:
    blocked = assign_label(
        data_quality_blocked=True,
        sample_sufficient=False,
        multiple_testing_rejected=True,
        cost_destroyed=True,
        bootstrap_stable=False,
        stability_axes_ok=False,
        dependence_blocks_robust=True,
    )
    assert blocked["label"] == "DATA_QUALITY_BLOCKED"
    sample = assign_label(
        data_quality_blocked=False,
        sample_sufficient=False,
        multiple_testing_rejected=True,
        cost_destroyed=True,
        bootstrap_stable=True,
        stability_axes_ok=True,
        dependence_blocks_robust=False,
    )
    assert sample["label"] == "INSUFFICIENT_SAMPLE"


def test_fixture_deterministic_and_lab_covers_labels() -> None:
    a = build_synthetic_candidates(seed=20260805)
    b = build_synthetic_candidates(seed=20260805)
    assert [c["candidate_id"] for c in a] == [c["candidate_id"] for c in b]
    assert a[0]["fixture_batch_digest"] == b[0]["fixture_batch_digest"]
    lab = run_robustness_lab(seed=20260805)
    assert lab["formal_walk_forward_executed"] is False
    assert lab["oos_consumed"] is False
    assert lab["qualification_ready_count"] == 0
    hist = lab["label_histogram"]
    for label in ALLOWED_LABELS:
        assert hist.get(label, 0) >= 1, f"missing pathway {label}: {hist}"
    adv = adversarial_self_review(lab)
    assert adv["adversarial_ok"] is True
    assert adv["critical_count"] == 0
    assert adv["high_count"] == 0


def test_lab_replay_stable() -> None:
    x = run_robustness_lab(seed=20260805)
    y = run_robustness_lab(seed=20260805)
    assert [e["label"] for e in x["evaluations"]] == [
        e["label"] for e in y["evaluations"]
    ]
    assert x["correlation_clustering"]["cluster_count"] == y[
        "correlation_clustering"
    ]["cluster_count"]
