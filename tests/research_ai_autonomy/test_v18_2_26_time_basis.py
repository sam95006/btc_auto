# -*- coding: utf-8 -*-
"""V18.2.26 — time-basis consistency + INVALID_HORIZON_CONFIGURATION + market funnel."""
from backend.nexus_research_ai_autonomy.horizon_feasibility import (
    INVALID_HORIZON_CONFIGURATION,
    build_horizon_plan,
    build_expected_move_curve,
    evaluate_horizon_feasibility,
    validate_horizon_configuration,
)
from backend.nexus_research_ai_autonomy.market_opportunity_selection import (
    rank_market_candidates,
    score_market_candidate,
)


def test_invalid_horizon_configuration_hard_lt_recommended_min():
    plan = build_horizon_plan(
        strategy_family="TREND",
        side="LONG",
        entry_price=64000.0,
        hard_max_hold_override=720,  # V25 bug: below 900 min
    )
    ok, reasons, block = validate_horizon_configuration(plan)
    assert ok is False
    assert block == INVALID_HORIZON_CONFIGURATION
    assert any("hard_max_hold" in r for r in reasons)


def test_same_horizon_curve_has_four_horizons():
    curve = build_expected_move_curve(atr_pct=0.5, activity=0.8, liquidity=0.9)
    assert len(curve) == 4
    horizons = [c.forecast_horizon_sec for c in curve]
    assert horizons == [300, 900, 1800, 3600]
    assert all(c.expected_move_method == "ATR_SQRT_TIME_SCALED" for c in curve)


def test_valid_horizon_plan_passes_integrity():
    plan = build_horizon_plan(
        strategy_family="TREND",
        side="LONG",
        entry_price=64000.0,
        realized_vol_pct_per_hour=1.2,
        regime="HIGH_VOLATILITY",
    )
    ok, _, _ = validate_horizon_configuration(plan)
    assert ok is True
    assert plan.hard_max_hold >= 900
    assert plan.forecast_horizon_sec is not None
    assert len(plan.expected_move_curve) == 4


def test_market_funnel_wait_when_no_candidates_pass():
    c = score_market_candidate(
        symbol="TESTUSDT",
        entry_price=1.0,
        equity=5000.0,
        vol_pct_per_hour=0.05,
        turnover24h=1000.0,
    )
    funnel = rank_market_candidates([c])
    assert funnel.action == "WAIT"
    assert funnel.block_code == "NO_ECONOMICALLY_FEASIBLE_MARKET_OPPORTUNITY"


def test_evaluate_blocks_invalid_config_before_mismatch():
    plan = build_horizon_plan(
        strategy_family="TREND",
        side="LONG",
        entry_price=64000.0,
        hard_max_hold_override=720,
    )
    h = evaluate_horizon_feasibility(plan=plan, economic_edge_pass=True)
    assert h.action == "WAIT"
    assert INVALID_HORIZON_CONFIGURATION in h.blocks
