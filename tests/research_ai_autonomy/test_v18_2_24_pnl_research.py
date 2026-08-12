# -*- coding: utf-8 -*-
"""V18.2.24 — risk sizing, economic filter, lifecycle purpose, entry≈exit audit."""
from backend.nexus_research_ai_autonomy.economic_entry_filter import evaluate_economic_entry
from backend.nexus_research_ai_autonomy.lifecycle_purpose import (
    LIFECYCLE_PURPOSE_EXECUTION_CANARY,
    LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
    audit_entry_exit_proximity,
    separate_counters,
)
from backend.nexus_research_ai_autonomy.position_manager import PositionManager
from backend.nexus_research_ai_autonomy.risk_based_sizing import compute_risk_based_size


def test_risk_based_size_preferred_band_and_max_loss():
    rs = compute_risk_based_size(
        equity=5022.93,
        entry_price=65000.0,
        stop_distance_pct=0.55,
        target_distance_pct=0.55,
        fee_rate_roundtrip=0.0011,
        slippage_pct=0.02,
        liquidity=0.95,
        confidence=0.75,
        qty_step=0.001,
        min_qty=0.001,
        min_notional=5.0,
    )
    assert rs.action == "SIZE"
    assert 250.0 - 1e-6 <= rs.notional_usdt <= 500.0 + 1.0  # step rounding slack
    assert rs.expected_loss_usdt <= rs.max_loss_usdt + 1e-6
    assert rs.leverage == 1
    assert rs.qty != 0.001 or rs.notional_usdt >= 250  # not fixed dust qty for PnL


def test_risk_based_size_waits_when_unsafe():
    rs = compute_risk_based_size(
        equity=100.0,  # tiny equity → max loss 0.1U
        entry_price=65000.0,
        stop_distance_pct=2.0,
        target_distance_pct=2.0,
        fee_rate_roundtrip=0.0011,
        slippage_pct=0.05,
        liquidity=0.95,
        confidence=0.9,
        qty_step=0.001,
        min_qty=0.001,
        min_notional=5.0,
    )
    assert rs.action == "WAIT"
    assert rs.qty == 0.0


def test_economic_entry_filter_preferred_1u():
    # 350 notional * 0.55% = 1.925 gross; fees ~0.385; slip ~0.07 → net ~1.47 PASS
    ok = evaluate_economic_entry(
        notional_usdt=350.0,
        target_distance_pct=0.55,
        roundtrip_fee_pct=0.11,
        slippage_pct=0.02,
    )
    assert ok.action == "PASS"
    assert ok.expected_net_profit_usdt >= 1.0

    thin = evaluate_economic_entry(
        notional_usdt=65.0,
        target_distance_pct=0.05,
        roundtrip_fee_pct=0.11,
        slippage_pct=0.02,
    )
    assert thin.action == "WAIT"
    assert "expected_net_below_preferred_1u" in thin.blocks


def test_entry_exit_audit_canary_forced_close():
    a = audit_entry_exit_proximity(
        entry_price=65065.0,
        exit_price=65045.0,
        hold_sec=2.0,
        exit_reason="reduce_only_or_max_hold",
        lifecycle_purpose=LIFECYCLE_PURPOSE_EXECUTION_CANARY,
        auto_close_immediate=True,
    )
    assert a["class"] == "CANARY_FORCED_CLOSE"
    assert a["economically_meaningless"] is True


def test_separate_counters_excludes_canaries_from_pnl():
    lives = [
        {
            "lifecycle_purpose": LIFECYCLE_PURPOSE_EXECUTION_CANARY,
            "bybit_orderId": "c1",
            "exchange_closed_pnl": {"closedPnl": "-0.07"},
            "process_class": "GOOD_PROCESS_LOSS",
        },
        {
            "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
            "bybit_orderId": "p1",
            "exchange_closed_pnl": {"closedPnl": "1.2"},
            "wallet_reconciliation": {"fees": "0.4"},
            "hold_sec": 120,
            "process_class": "GOOD_PROCESS_WIN",
        },
    ]
    c = separate_counters(lives)
    assert c["execution_canaries"]["n"] == 1
    assert c["execution_canaries"]["counted_in_strategy_wins_losses"] is False
    assert c["pnl_research_trades"]["n"] == 1
    assert c["pnl_research_trades"]["wins"] == 1


def test_position_manager_no_mandatory_min_hold_for_pnl_research():
    """V18.2.25: no arbitrary mandatory min hold — AI EXIT allowed (Risk still gates)."""
    pm = PositionManager()
    pos = pm.open_from_execution(
        decision={
            "decision_id": "d1",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "stop_logic": {"price": 64000},
            "take_profit_logic": {"price": 66000},
            "max_hold": 900,
            "min_hold_sec": 90,  # ignored for RESEARCH_PNL_TRADE under V25
            "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
            "regime": "TREND_UP",
            "trail_pct": 0.25,
        },
        fill_price=65000.0,
        qty=0.005,
    )
    out = pm.manage_cycle(
        pos.position_id,
        market={"last_price": 65010.0, "liquidity": 0.9},
        regime="TREND_UP",
        ai_proposal="EXIT",
    )
    assert out["action"] == "EXIT"
    assert pos.min_hold_sec == 0

