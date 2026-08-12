# -*- coding: utf-8 -*-
"""V18.2.25 — horizon feasibility, exact PnL accounting, exit quality, CA5 H02 decomp."""
from backend.nexus_demo_execution.pnl_accounting import build_exact_pnl_breakdown
from backend.nexus_research_ai_autonomy.exit_quality import (
    PathExcursionTracker,
    canonicalize_exit_reason,
    classify_exit_quality,
)
from backend.nexus_research_ai_autonomy.horizon_feasibility import (
    build_horizon_plan,
    evaluate_horizon_feasibility,
)
from backend.nexus_research_ai_autonomy.position_manager import PositionManager
from backend.nexus_strategy_engine.ca5_dev_cycle import decompose_h02_weakness


def test_horizon_mismatch_waits_does_not_shrink_target():
    plan = build_horizon_plan(
        strategy_family="TREND",
        side="LONG",
        entry_price=64000.0,
        expected_target_move_pct=0.55,
        stop_move_pct=0.40,
        realized_vol_pct_per_hour=0.15,  # low vol → mismatch
        regime="LOW_VOLATILITY",
        activity_score=0.5,
        liquidity=0.9,
    )
    h = evaluate_horizon_feasibility(plan=plan, economic_edge_pass=True)
    assert h.action == "WAIT"
    assert h.horizon_feasibility_pass is False
    assert "HORIZON_TARGET_MISMATCH" in h.blocks
    assert h.shrunk_target_to_force_entry is False
    assert plan.expected_target_move_pct == 0.55  # not shrunk


def test_horizon_pass_when_vol_covers_target():
    plan = build_horizon_plan(
        strategy_family="TREND",
        side="LONG",
        entry_price=64000.0,
        expected_target_move_pct=0.55,
        stop_move_pct=0.40,
        realized_vol_pct_per_hour=1.2,
        regime="HIGH_VOLATILITY",
        activity_score=1.0,
        liquidity=1.0,
    )
    h = evaluate_horizon_feasibility(plan=plan, economic_edge_pass=True)
    assert h.horizon_feasibility_pass is True
    assert h.action == "PASS"
    assert plan.hard_max_hold >= 900  # not generic 180s


def test_exact_pnl_fee_inclusive_no_double_count():
    # V24-like: closedPnl=-0.343, fees=0.353, wallet_delta=-0.343
    b = build_exact_pnl_breakdown(
        exchange_closed_pnl="-0.34309373",
        open_fee="0.17629425",
        close_fee="0.17629948",
        funding="0",
        wallet_before="5027.78143134",
        wallet_after="5027.43833761",
        side="LONG",
        qty="0.005",
        entry_price="64107",
        exit_price="64108.9",
    )
    assert b["closedPnl_fee_inclusive"] is True
    assert b["identities"]["fees_not_double_counted"] is True
    assert b["identities"]["exchange_closed_approx_wallet_delta"] is True
    assert float(b["calculated_net_pnl"]) == float(b["exchange_closed_pnl"])
    # price before fees ≈ closed + fees
    assert abs(float(b["price_pnl_before_fees"]) - (float(b["exchange_closed_pnl"]) + float(b["total_fees"]))) < 1e-6


def test_exit_reason_canonical_and_mfe_tracking():
    assert canonicalize_exit_reason("max_hold") == "STRATEGY_HORIZON_EXPIRED"
    assert canonicalize_exit_reason("take_profit") == "TAKE_PROFIT"
    pm = PositionManager()
    pos = pm.open_from_execution(
        decision={
            "decision_id": "d1",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "strategy_family": "TREND",
            "regime": "TREND_UP",
            "hard_max_hold": 120,
            "max_hold": 120,
            "stop_price": 100.0,
            "target_price": 110.0,
            "lifecycle_purpose": "RESEARCH_PNL_TRADE",
        },
        fill_price=105.0,
        qty=1.0,
    )
    r = pm.manage_cycle(pos.position_id, market={"last_price": 107.0, "liquidity": 0.9}, regime="TREND_UP")
    assert r["action"] == "HOLD"
    assert pos.path_tracker is not None
    assert pos.path_tracker.mfe_usdt > 0
    r2 = pm.manage_cycle(
        pos.position_id, market={"last_price": 110.0, "liquidity": 0.9}, regime="TREND_UP"
    )
    assert r2["action"] == "EXIT"
    assert r2["reason"] == "TAKE_PROFIT"


def test_path_excursion_tracker_updates():
    tr = PathExcursionTracker(
        entry_price=100.0, side="LONG", qty=1.0, target_price=101.0, stop_price=99.0, opened_at_ms=0
    )
    tr.update(100.5, now_ms=1000)
    assert tr.mfe_usdt > 0
    tr.update(99.5, now_ms=2000)
    assert tr.mae_usdt < 0


def test_exit_quality_diagnostic_only():
    q = classify_exit_quality(
        exit_reason="STRATEGY_HORIZON_EXPIRED",
        realized_usdt=-0.34,
        mfe_usdt=0.01,
        mae_usdt=-0.02,
        target_touched=False,
        stop_touched=False,
        hold_sec=186.0,
        hard_max_hold=180.0,
        expected_target_move_pct=0.55,
        expected_path_range_pct=0.20,
    )
    assert q["diagnostic_only"] is True
    assert q["auto_rewrite_live_strategy"] is False
    assert q["exit_quality_class"] in {
        "TARGET_WAS_UNREALISTIC_FOR_HORIZON",
        "NO_EDGE_AFTER_ENTRY",
        "UNKNOWN",
    }


def test_ca5_h02_decomposition_preregisters_at_most_two():
    decomp = decompose_h02_weakness(
        h02_variant={
            "PRE_WF_READY": False,
            "PASS": True,
            "cost_stress": {"net_at_1.0x": 0.25, "net_at_2.0x": -0.2},
            "break_even_cost_multiplier": 1.4,
            "turnover_events_per_trade": 1.4,
            "net_edge_per_trade": 0.25,
        },
        baseline_turnover=2.6,
        baseline_net_edge=0.22,
        regime_share=0.51,
        independence={"effective_independent_n": 5.4, "design_effect": 90.0},
        raw_n=490,
    )
    assert decomp["dev_only"] is True
    assert decomp["oos"] is False
    assert decomp["successor_count"] <= 2
    assert decomp["blind_threshold_tuning"] is False
    assert len(decomp["dominant_weaknesses"]) >= 1
