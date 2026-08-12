# -*- coding: utf-8 -*-
"""V18.2.26 — time-basis consistency, full-market selection, horizon config validation."""
from backend.nexus_research_ai_autonomy.horizon_feasibility import (
    STANDARD_FORECAST_HORIZONS_SEC,
    build_expected_move_curve,
    build_horizon_plan,
    validate_horizon_configuration,
)
from backend.nexus_research_ai_autonomy.market_opportunity_selection import (
    MarketCandidate,
    select_best_market_opportunity,
)
from backend.nexus_research_ai_autonomy.prepared_decision import validate_prepared_decision_horizon
from backend.nexus_research_ai_autonomy.time_basis import evaluate_compatible_horizon_feasibility
from backend.nexus_strategy_engine.ca5_dev_cycle import (
    CA5_SUCCESSORS,
    run_ca5_successor_development,
)


def test_expected_move_curve_has_four_horizons():
    curve = build_expected_move_curve(atr_pct=0.5, activity=0.8, liquidity=0.9)
    assert len(curve) == 4
    horizons = {e.forecast_horizon_sec for e in curve}
    assert horizons == set(STANDARD_FORECAST_HORIZONS_SEC)
    for e in curve:
        assert e.expected_move_pct > 0
        assert e.expected_move_method
        assert e.volatility_window
        assert e.sample_timestamp > 0


def test_invalid_horizon_configuration_blocks():
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


def test_compatible_horizon_no_mismatch():
    curve = build_expected_move_curve(atr_pct=1.2, activity=1.0, liquidity=1.0)
    r = evaluate_compatible_horizon_feasibility(
        target_move_pct=0.55,
        strategy_horizon_sec=1800,
        curve=[e.to_dict() for e in curve],
        economic_edge_pass=True,
    )
    assert r["time_basis"] == "COMPATIBLE_HORIZON"
    assert r["strategy_horizon_sec"] == 1800


def test_low_vol_compatible_horizon_waits():
    curve = build_expected_move_curve(atr_pct=0.12, activity=0.5, liquidity=0.9)
    r = evaluate_compatible_horizon_feasibility(
        target_move_pct=0.55,
        strategy_horizon_sec=1800,
        curve=[e.to_dict() for e in curve],
        economic_edge_pass=True,
    )
    assert r["horizon_feasibility_pass"] is False
    assert "HORIZON_TARGET_MISMATCH" in r["blocks"]


def test_prepared_decision_horizon_validation():
    val = validate_prepared_decision_horizon(
        {
            "hard_max_hold": 720,
            "recommended_hold_window": [900, 3600],
            "expected_time_to_target": 1200,
            "economic_edge_pass": True,
            "horizon_feasibility_pass": False,
        }
    )
    assert val["action"] == "REJECT"
    assert val["status_blocker"] == "INVALID_HORIZON_CONFIGURATION"


def test_full_market_wait_when_none_pass():
    cands = [
        MarketCandidate(
            symbol="XUSDT",
            strategy_family="TREND",
            direction="LONG",
            entry_price=1.0,
            rejection_reason="liquidity_too_thin",
        )
    ]
    sel = select_best_market_opportunity(cands)
    assert sel["action"] == "WAIT"
    assert sel["block_code"] == "NO_ECONOMICALLY_FEASIBLE_MARKET_OPPORTUNITY"


def test_ca5_successor_dev_executes_s01_s02():
    prior = {
        "variants": [
            {
                "candidate_id": "V18_CA5_H02_SELECTIVITY_HORIZON",
                "cost_stress": {
                    "net_at_1.0x": 0.26,
                    "net_at_1.25x": 0.065,
                    "net_at_1.5x": -0.13,
                    "net_at_2.0x": -0.52,
                },
                "break_even_cost_multiplier": 1.54,
                "turnover_events_per_trade": 1.45,
                "raw_n": 171,
                "regime_slices": {"largest_regime_profit_contribution": 0.51},
                "sample_independence": {"effective_independent_n": 6.5, "mean_within_group_corr": 0.45},
                "symbol_group_slices": {},
                "time_block_slices": {},
            }
        ],
        "h02_failure_decomposition": {"successor_hypotheses": [], "dominant_weaknesses": ["FEE_LOAD"]},
    }
    out = run_ca5_successor_development(
        prior_ca5=prior,
        ca2_baseline={"net_at_1.0x": 0.22},
        ca3_baseline={"net_at_1.0x": 0.22},
        ca5_holdout_hash="abc",
    )
    assert out["development_executed"] is True
    ids = [s["candidate_id"] for s in out["successors"]]
    assert ids == list(CA5_SUCCESSORS)
    assert out["OOS"]["OOS_executed"] is False
    assert out["PRE_WF"]["forced"] is False
