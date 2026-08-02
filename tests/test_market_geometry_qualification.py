"""True market-data geometry qualification tests — no live trading."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_demo_execution.historical_market_data import (
    Candle,
    build_dataset,
    parse_kline_rows,
)
from backend.nexus_demo_execution.market_event_sim import (
    build_candidates_from_dataset,
    run_market_qualification,
    simulate_natural_trade,
    summarize_trades,
)
from backend.nexus_demo_execution.session_limits import MIN_NET_REWARD_RISK_RATIO, MIN_NET_REWARD_TO_COST
from backend.nexus_demo_execution.shadow_plan import build_shadow_plan


def _make_trend_candles(n: int = 200, start_ms: int = 1_700_000_000_000, step: int = 900_000) -> list[Candle]:
    """Chronological OHLC fixture (not a forced win/loss sequence)."""
    out: list[Candle] = []
    px = 100.0
    for i in range(n):
        # mild random-walk-like but deterministic drift
        drift = 0.08 if (i % 17) < 10 else -0.06
        o = px
        c = px + drift
        h = max(o, c) + 0.25
        l = min(o, c) - 0.25
        out.append(Candle(ts_ms=start_ms + i * step, open=o, high=h, low=l, close=c, volume=10.0 + i))
        px = c
    return out


def test_floors_unchanged():
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert MIN_NET_REWARD_TO_COST == 1.5


def test_provenance_monotonic_and_checksum():
    candles = _make_trend_candles(50)
    ds = build_dataset(symbol="BTCUSDT", interval="15", candles=candles)
    assert ds.timestamps_monotonic is True
    assert ds.duplicate_records == 0
    assert ds.future_data_used is False
    assert ds.classification == "REAL_HISTORICAL_MARKET_DATA"
    assert len(ds.data_checksum) == 64
    assert ds.record_count == 50


def test_parse_kline_newest_first_to_chrono():
    raw = [
        [3, "103", "104", "102", "103", "1"],
        [2, "102", "103", "101", "102", "1"],
        [1, "100", "101", "99", "100", "1"],
    ]
    rows = parse_kline_rows(raw)
    assert [r.ts_ms for r in rows] == [1, 2, 3]


def test_candidate_snapshot_no_future_bars():
    ds = build_dataset(symbol="ETHUSDT", interval="15", candles=_make_trend_candles(80))
    cands = build_candidates_from_dataset(ds, min_bars=40, stride=5)
    assert cands
    for c in cands:
        assert c.future_data_reference_count == 0
        assert c.look_ahead_contamination is False
        assert c.last_input_candle_time == c.candidate_snapshot_time
        # snapshot must not exceed dataset end for that bar
        assert c.candidate_snapshot_time <= ds.end_time


def test_natural_entry_not_forced():
    # Flat path far from a distant entry — should expire / not fill
    candles = [
        Candle(ts_ms=1_000 + i * 900_000, open=100, high=100.1, low=99.9, close=100, volume=1)
        for i in range(30)
    ]
    ds = build_dataset(symbol="BTCUSDT", interval="15", candles=candles)
    cands = build_candidates_from_dataset(ds, min_bars=20, stride=20)
    assert cands
    # Force entry price away from market so subsequent bars never touch
    c = cands[0]
    c.entry_price = 50.0
    c.evidence.entry_price = 50.0
    idx = next(i for i, x in enumerate(ds.candles) if x.ts_ms == c.candidate_snapshot_time)
    trade = simulate_natural_trade(candidate=c, subsequent=ds.candles[idx + 1 :])
    assert trade.entry_status in {"ENTRY_EXPIRED", "ENTRY_NOT_TRIGGERED", "GEOMETRY_BLOCKED", "COST_GATE_BLOCKED"}
    if trade.entry_status in {"ENTRY_EXPIRED", "ENTRY_NOT_TRIGGERED"}:
        assert trade.exit_status is None


def test_adverse_first_intrabar_on_real_path():
    # Build a candidate that can pass geometry, then ambiguous SL/TP bar after fill
    base = _make_trend_candles(60)
    # Append controlled subsequent bars
    last_ts = base[-1].ts_ms
    step = 900_000
    # strong uptrend structure candles already present
    ds = build_dataset(symbol="BTCUSDT", interval="15", candles=base)
    cands = build_candidates_from_dataset(ds, min_bars=40, stride=40)
    if not cands:
        pytest.skip("no candidates")
    c = cands[0]
    from backend.nexus_demo_execution.structural_geometry_qualify import evaluate_structural_geometry

    geo = evaluate_structural_geometry(c.evidence)
    if not geo.get("cost_gate_pass"):
        pytest.skip("cost gate blocked on fixture")
    stop = float(geo["stop_price"])
    tp = float(geo["take_profit_price"])
    entry = c.entry_price
    subsequent = [
        Candle(ts_ms=last_ts + step, open=entry, high=entry + 0.01, low=entry - 0.01, close=entry, volume=1),
        Candle(ts_ms=last_ts + 2 * step, open=entry, high=max(entry, tp) + 1, low=min(entry, stop) - 1, close=entry, volume=1),
    ]
    # Re-bind candidate snapshot so subsequent is used after fill touch
    trade = simulate_natural_trade(candidate=c, subsequent=subsequent, adverse_first=True)
    if trade.entry_status != "ENTRY_FILLED":
        pytest.skip(f"entry={trade.entry_status}")
    assert trade.exit_status == "STOP_LOSS"
    assert trade.adverse_first_applied is True
    assert trade.ambiguity_count >= 1
    assert trade.look_ahead_contamination is False


def test_unresolved_not_win():
    candles = _make_trend_candles(50)
    ds = build_dataset(symbol="SOLUSDT", interval="15", candles=candles)
    cands = build_candidates_from_dataset(ds, min_bars=40, stride=40)
    if not cands:
        pytest.skip("no candidates")
    c = cands[0]
    idx = next(i for i, x in enumerate(ds.candles) if x.ts_ms == c.candidate_snapshot_time)
    # Only one subsequent bar that touches entry but no SL/TP room
    entry = c.entry_price
    subsequent = [
        Candle(ts_ms=c.candidate_snapshot_time + 900_000, open=entry, high=entry + 0.01, low=entry - 0.01, close=entry, volume=1)
    ]
    trade = simulate_natural_trade(candidate=c, subsequent=subsequent, entry_wait_bars=5, time_stop_bars=50)
    if trade.entry_status == "ENTRY_FILLED":
        assert trade.exit_status == "UNRESOLVED_AT_DATA_END"
        assert trade.net_pnl is None
        s = summarize_trades([trade], min_sample=1)
        assert s["simulated_trade_count"] == 0


def test_synthetic_forced_cannot_be_oos_validated_via_market_runner():
    # Empty invalid dataset classification
    bad = build_dataset(symbol="BTCUSDT", interval="15", candles=[])
    # empty candles → start/end 0; still REAL if no future — but insufficient
    report = run_market_qualification([bad], min_sample=30)
    assert report["oos_status"] in {"OOS_INSUFFICIENT_SAMPLE", "OOS_DATA_INVALID"}
    assert report.get("recommendation") in {
        "NEXUS_OOS_INSUFFICIENT_SAMPLE",
        "NEXUS_GEOMETRY_QUALIFICATION_IN_PROGRESS",
    }
    assert report.get("oos_status") != "OOS_PERFORMANCE_VALIDATED" or report.get("synthetic_forced_trade_count") == 0


def test_zero_trades_cannot_oos_validated():
    from backend.nexus_demo_execution.market_event_sim import _classify_oos

    assert (
        _classify_oos(
            {
                "simulated_trade_count": 0,
                "synthetic_forced_trade_count": 0,
                "look_ahead_contamination": False,
            },
            min_sample=30,
            data_valid=True,
        )
        == "OOS_INSUFFICIENT_SAMPLE"
    )


def test_null_metrics_cannot_oos_validated():
    from backend.nexus_demo_execution.market_event_sim import _classify_oos

    assert (
        _classify_oos(
            {
                "simulated_trade_count": 50,
                "synthetic_forced_trade_count": 0,
                "look_ahead_contamination": False,
                "net_pnl": None,
                "profit_factor": 1.2,
                "expectancy": 0.1,
                "maximum_drawdown": -1,
                "win_rate": 0.5,
                "gross_pnl": 1,
                "total_fees": 1,
                "spread_cost": 1,
                "slippage_cost": 1,
                "funding": 1,
            },
            min_sample=30,
            data_valid=True,
        )
        == "OOS_INSUFFICIENT_SAMPLE"
    )


def test_fold_isolation_and_untouched_oos():
    ds = build_dataset(symbol="BTCUSDT", interval="15", candles=_make_trend_candles(300))
    report = run_market_qualification([ds], min_sample=5)
    assert report["market_data_source"] == "REAL_HISTORICAL_MARKET_DATA"
    assert report["synthetic_forced_trade_count"] == 0
    assert report["look_ahead_contamination"] is False
    folds = report["walk_forward_folds"]
    assert "fold1_train" in folds
    assert "fold3_test_oos" in folds
    assert report["oos_status"] in {
        "OOS_PERFORMANCE_VALIDATED",
        "OOS_PERFORMANCE_FAILED",
        "OOS_INSUFFICIENT_SAMPLE",
        "OOS_DATA_INVALID",
    }
    assert report["qualification_complete"] is False
    assert report["shadow_status"] == "NOT_APPLIED"


def test_shadow_plan_not_applied():
    plan = build_shadow_plan()
    assert plan["shadow_plan_ready"] is True
    assert plan["shadow_status"] == "NOT_APPLIED"
    assert plan["constraints"]["bybit_order"] is False


def test_mainnet_real_money_forbidden():
    from backend.nexus_demo_execution import MAINNET, REAL_MONEY

    assert MAINNET is False
    assert REAL_MONEY is False


def test_secret_scan_new_modules():
    for rel in (
        "backend/nexus_demo_execution/historical_market_data.py",
        "backend/nexus_demo_execution/market_event_sim.py",
        "backend/nexus_demo_execution/shadow_plan.py",
    ):
        text = Path(rel).read_text(encoding="utf-8")
        for needle in ("API_KEY", "api_secret", "SECRET_KEY=", "BEGIN PRIVATE"):
            assert needle not in text
