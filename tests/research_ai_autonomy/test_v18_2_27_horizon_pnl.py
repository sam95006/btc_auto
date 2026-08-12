# -*- coding: utf-8 -*-
"""V18.2.27 — horizon integrity + canonical funnel + no SESSION_OBSERVE_CAP."""
from backend.nexus_research_ai_autonomy.horizon_feasibility import build_horizon_plan, validate_horizon_configuration
from backend.nexus_research_ai_autonomy.market_opportunity_selection import (
    MarketCandidate,
    build_canonical_funnel_stages,
    select_best_market_opportunity,
)
from backend.nexus_research_ai_autonomy.position_lifecycle_manager import evaluate_horizon_integrity
from backend.nexus_strategy_engine.ca5_dev_cycle import (
    CA5_SUCCESSORS,
    run_ca5_s01_s02_diagnostic_comparison,
    run_ca5_successor_development,
)


def test_strategy_config_hard_max_no_session_cap():
    plan = build_horizon_plan(
        strategy_family="TREND",
        side="LONG",
        entry_price=64000.0,
        realized_vol_pct_per_hour=0.5,
    )
    ok, _, block = validate_horizon_configuration(plan)
    assert ok is True
    assert plan.hard_max_hold >= plan.recommended_hold_window[0]
    assert plan.hard_max_hold >= 900
    assert block is None


def test_invalid_horizon_configuration_still_blocks():
    plan = build_horizon_plan(
        strategy_family="TREND",
        side="LONG",
        entry_price=64000.0,
        realized_vol_pct_per_hour=0.5,
        hard_max_hold_override=720,
    )
    ok, reasons, block = validate_horizon_configuration(plan)
    assert ok is False
    assert block == "INVALID_HORIZON_CONFIGURATION"
    assert reasons


def test_horizon_integrity_gate():
    r = evaluate_horizon_integrity(strategy_family="TREND")
    assert r["horizon_integrity_pass"] is True
    assert r["invariant_hard_max_gte_window_min"] is True


def test_canonical_funnel_stages_order():
    cands = [
        MarketCandidate(
            symbol="AUSDT",
            strategy_family="TREND",
            direction="LONG",
            entry_price=1.0,
            economic_edge_pass=True,
            horizon_feasibility_pass=True,
            horizon_config_valid=True,
            risk_pass=True,
            rank_score=1.0,
        ),
        MarketCandidate(
            symbol="BUSDT",
            strategy_family="TREND",
            direction="LONG",
            entry_price=1.0,
            rejection_reason="liquidity_too_thin",
        ),
    ]
    stages = build_canonical_funnel_stages(cands)
    assert stages["eligible"] == 2
    assert stages["liquidity_data_pass"] == 1
    assert stages["economic_pass"] == 1
    assert stages["horizon_pass"] == 1
    assert stages["risk_pass"] == 1
    assert stages["prepared"] == 1
    sel = select_best_market_opportunity(cands)
    assert "liquidity_data_pass" in sel["funnel"]
    assert sel["funnel"]["canonical_order"][0] == "eligible"


def test_ca5_s01_s02_diagnostic_only():
    prior = {
        "variants": [
            {
                "candidate_id": "V18_CA5_H02_SELECTIVITY_HORIZON",
                "cost_stress": {"net_at_1.0x": 0.26},
                "break_even_cost_multiplier": 1.54,
                "turnover_events_per_trade": 1.45,
                "raw_n": 171,
                "sample_independence": {"effective_independent_n": 6.5, "mean_within_group_corr": 0.45},
                "regime_slices": {"largest_regime_profit_contribution": 0.51},
            }
        ],
        "h02_failure_decomposition": {"dominant_weaknesses": ["FEE_LOAD"]},
    }
    dev = run_ca5_successor_development(
        prior_ca5=prior,
        ca2_baseline={"net_at_1.0x": 0.22},
        ca3_baseline={"net_at_1.0x": 0.22},
        ca5_holdout_hash="abc",
    )
    diag = run_ca5_s01_s02_diagnostic_comparison(prior_ca5=prior, successor_dev=dev)
    assert diag["diagnostic_only"] is True
    assert diag["successors_evaluated"] == list(CA5_SUCCESSORS)
    assert "S03" in diag["excluded"]
    assert diag["preferred_structural_path"] in CA5_SUCCESSORS
    assert diag["OOS_executed"] is False
    assert diag["PRE_WF_forced"] is False
