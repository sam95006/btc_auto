"""Cohort edge research unit tests — offline, no secrets, no mainnet."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_demo_execution.cohort_edge_research import (
    _edge_class,
    _qualify_status,
    build_cohort_candidates,
)
from backend.nexus_demo_execution.cohort_matrix import (
    COHORT_SPECS,
    DATA_UNAVAILABLE_STRATEGIES,
    confirm_entry,
    build_context,
)
from backend.nexus_demo_execution.historical_market_data import Candle, MarketDataset
from backend.nexus_demo_execution.oos_risk_audit import CONSUMED_STATUS
from backend.nexus_demo_execution.session_limits import MIN_NET_REWARD_RISK_RATIO, MIN_NET_REWARD_TO_COST


def _synth_dataset(symbol: str = "BTCUSDT", n: int = 120, trend: str = "up") -> MarketDataset:
    candles: list[Candle] = []
    px = 100_000.0
    for i in range(n):
        if trend == "up":
            px *= 1.0008
        elif trend == "down":
            px *= 0.9992
        else:
            px *= 1.0001 if i % 2 == 0 else 0.9999
        o = px
        h = px * 1.001
        l = px * 0.999
        c = px * (1.0004 if trend == "up" else (0.9996 if trend == "down" else 1.0))
        candles.append(
            Candle(ts_ms=1_700_000_000_000 + i * 900_000, open=o, high=h, low=l, close=c, volume=1000 + i)
        )
        px = c
    return MarketDataset(
        exchange="bybit",
        market_type="linear",
        symbol=symbol,
        interval="15",
        start_time=candles[0].ts_ms,
        end_time=candles[-1].ts_ms,
        record_count=len(candles),
        downloaded_at=0.0,
        source_endpoint="/v5/market/kline",
        data_checksum="synth",
        missing_interval_count=0,
        duplicate_interval_count=0,
        timestamps_monotonic=True,
        duplicate_records=0,
        future_data_used=False,
        candles=candles,
        classification="SYNTH_TEST",
    )


def test_floors_unchanged():
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert MIN_NET_REWARD_TO_COST == 1.5


def test_cohort_matrix_includes_baseline_and_unavailable():
    ids = {(s, r, side) for s, r, side in COHORT_SPECS}
    assert ("STRUCT_SWING", "RANGE", "Buy") in ids
    assert ("trend_following", "TRENDING_UP", "Buy") in ids
    assert "funding_oi_contrarian" in DATA_UNAVAILABLE_STRATEGIES


def test_confirm_entry_rejects_data_unavailable():
    ds = _synth_dataset(trend="up")
    ctx = build_context(ds.candles)
    ok, reason = confirm_entry("funding_oi_contrarian", "EXTREME_POSITIONING", "Buy", ctx)
    assert ok is False
    assert reason == "DATA_UNAVAILABLE"


def test_build_cohort_candidates_no_lookahead_fields():
    ds = _synth_dataset(trend="up")
    cands = build_cohort_candidates(ds, stride=10)
    assert all(c.look_ahead_contamination is False for c in cands)
    assert all(c.future_data_reference_count == 0 for c in cands)


def test_edge_class_rejects_marginal_gross():
    cost = {
        "GROSS_NO_COST_DIAGNOSTIC": {
            "completed_trade_count": 30,
            "gross_profit_factor": 1.005,
            "gross_expectancy": 0.006,
        },
        "BASE_CONSERVATIVE_COST": {"completed_trade_count": 30, "net_profit_factor": 0.5},
        "ADVERSE_COST_STRESS": {"completed_trade_count": 30, "net_profit_factor": 0.4},
    }
    assert _edge_class(cost) == "NO_GROSS_EDGE"


def test_qualify_rejects_without_surviving_cost():
    replay = {
        "completed_trade_count": 40,
        "gross_expectancy": 0.5,
        "net_expectancy": 0.2,
        "net_profit_factor": 1.2,
        "maximum_drawdown": -5.0,
        "symbols": ["BTCUSDT", "ETHUSDT"],
    }
    status = _qualify_status(replay=replay, fold_results=[], edge="NO_GROSS_EDGE")
    assert status == "REJECTED"


def test_consumed_oos_status_constant():
    assert CONSUMED_STATUS == "CONSUMED_FAILED_HOLDOUT"


def test_mainnet_real_money_forbidden():
    from backend.nexus_demo_execution import MAINNET, REAL_MONEY

    assert MAINNET is False
    assert REAL_MONEY is False


def test_secret_scan_cohort_modules():
    for rel in (
        "backend/nexus_demo_execution/cohort_matrix.py",
        "backend/nexus_demo_execution/cohort_edge_research.py",
    ):
        text = Path(rel).read_text(encoding="utf-8")
        for needle in ("API_KEY", "api_secret", "SECRET_KEY=", "BEGIN PRIVATE"):
            assert needle not in text
        assert "api.bybit.com" not in text
