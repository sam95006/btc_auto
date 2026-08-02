"""Risk sizing + OOS integrity audit tests."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_demo_execution.oos_risk_audit import CONSUMED_STATUS, compute_mfe_mae
from backend.nexus_demo_execution.risk_sizing import detect_sizing_defects, liquidation_price, size_position
from backend.nexus_demo_execution.session_limits import (
    FIXED_LEVERAGE,
    MARGIN_PER_TRADE_CAP,
    MAX_SINGLE_TRADE_NET_LOSS,
)
from backend.nexus_demo_execution.historical_market_data import Candle


def test_fixed_margin_and_leverage_constants():
    assert MARGIN_PER_TRADE_CAP == 20.0
    assert FIXED_LEVERAGE == 25
    assert MAX_SINGLE_TRADE_NET_LOSS == 3.0


def test_leverage_not_multiplied_twice():
    s = size_position(
        symbol="BTCUSDT",
        side="Buy",
        entry_price=100_000.0,
        stop_price=99_400.0,  # 0.6% stop → risk/unit=600
        take_profit_price=101_200.0,
        qty_step=0.001,
        min_order_qty=0.001,
        min_notional=5.0,
    )
    # qty_by_margin = 500/100000 = 0.005; qty_by_risk = 3/600 = 0.005
    assert s.desired_notional == 500.0
    assert abs(s.quantity_by_margin - 0.005) < 1e-9
    assert s.notional <= 500.0 + 1e-6
    # Must not be margin * leverage^2 / price
    assert s.notional < 500.0 * FIXED_LEVERAGE * 0.5


def test_risk_based_quantity_cap():
    # Wide stop → risk qty smaller than margin qty
    s = size_position(
        symbol="ETHUSDT",
        side="Buy",
        entry_price=2000.0,
        stop_price=1900.0,  # risk/unit=100 → qty_risk=0.03; qty_margin=500/2000=0.25
        take_profit_price=2200.0,
        qty_step=0.01,
        min_order_qty=0.01,
        min_notional=5.0,
    )
    assert s.quantity <= s.quantity_by_risk + 1e-12
    assert s.maximum_possible_loss <= MAX_SINGLE_TRADE_NET_LOSS + 1e-6


def test_max_3u_trade_loss_enforced():
    s = size_position(
        symbol="BTCUSDT",
        side="Buy",
        entry_price=100_000.0,
        stop_price=99_000.0,
        qty_step=0.001,
        min_order_qty=0.001,
    )
    if s.allowed:
        assert s.maximum_possible_loss <= MAX_SINGLE_TRADE_NET_LOSS + 1e-6


def test_liquidation_and_stop_beyond_rejection():
    liq = liquidation_price(entry_price=100.0, side="Buy", leverage=25)
    assert liq < 100.0
    # Stop below liquidation
    s = size_position(
        symbol="BTCUSDT",
        side="Buy",
        entry_price=100.0,
        stop_price=liq - 1.0,
        qty_step=0.001,
        min_order_qty=0.001,
        min_notional=5.0,
    )
    assert s.allowed is False
    assert s.block_reason == "BLOCK_LIQUIDATION_TOO_CLOSE"


def test_fee_on_notional_only_detection_helpers():
    det = detect_sizing_defects(
        entry_price=100_000.0,
        qty=1.0,
        stop_price=99_000.0,
        side="Buy",
        net_pnl=-1000.0,
    )
    assert "POSITION_SIZING_OFF_TARGET" in det["defects"]
    assert "RISK_BUDGET_BREACH" in det["defects"]


def test_gross_diagnostic_does_not_zero_evidence_fee():
    """fee_rate<=0 on evidence triggers FEE_RATE_UNKNOWN — gross must zero costs at PnL only."""
    from backend.nexus_demo_execution.structural_geometry_qualify import CandidateEvidence, evaluate_structural_geometry

    ev = CandidateEvidence(
        symbol="BTCUSDT",
        side="Buy",
        entry_price=100_000.0,
        atr=500.0,
        recent_swing_high=101_000.0,
        recent_swing_low=99_000.0,
        support=99_200.0,
        resistance=100_800.0,
        fee_rate=0.00055,
        spread_bps=2.0,
        slippage_bps=2.0,
        qty=0.005,
    )
    g_ok = evaluate_structural_geometry(ev)
    assert g_ok.get("geometry_invalid") is not True or g_ok.get("block_reason") != "FEE_RATE_UNKNOWN"
    ev_bad = CandidateEvidence(
        symbol="BTCUSDT",
        side="Buy",
        entry_price=100_000.0,
        atr=500.0,
        recent_swing_high=101_000.0,
        recent_swing_low=99_000.0,
        support=99_200.0,
        resistance=100_800.0,
        fee_rate=0.0,
        qty=0.005,
    )
    g_bad = evaluate_structural_geometry(ev_bad)
    assert g_bad.get("block_reason") == "FEE_RATE_UNKNOWN" or g_bad.get("geometry_invalid") is True


def test_qty_rounds_to_zero_block():
    s = size_position(
        symbol="BTCUSDT",
        side="Buy",
        entry_price=100_000.0,
        stop_price=99_999.0,
        qty_step=1.0,  # absurd step forces zero
        min_order_qty=1.0,
        min_notional=5.0,
    )
    assert s.allowed is False
    assert s.block_reason in {"BLOCK_QUANTITY_ROUNDS_TO_ZERO", "BLOCK_INSTRUMENT_MINIMUM_NOT_MET"}


def test_mfe_mae_diagnostic_only():
    bars = [
        Candle(ts_ms=1, open=100, high=101, low=99.5, close=100.5, volume=1),
        Candle(ts_ms=2, open=100.5, high=102, low=100, close=101, volume=1),
    ]
    out = compute_mfe_mae(side="Buy", entry_price=100.0, stop=99.0, subsequent_after_fill=bars)
    assert out["mfe"] >= 2.0
    assert out["mae"] >= 0.5


def test_consumed_oos_status_constant():
    assert CONSUMED_STATUS == "CONSUMED_FAILED_HOLDOUT"


def test_mainnet_real_money_forbidden():
    from backend.nexus_demo_execution import MAINNET, REAL_MONEY

    assert MAINNET is False
    assert REAL_MONEY is False


def test_secret_scan_risk_modules():
    for rel in (
        "backend/nexus_demo_execution/risk_sizing.py",
        "backend/nexus_demo_execution/oos_risk_audit.py",
    ):
        text = Path(rel).read_text(encoding="utf-8")
        for needle in ("API_KEY", "api_secret", "SECRET_KEY=", "BEGIN PRIVATE"):
            assert needle not in text
        assert "api.bybit.com" not in text
