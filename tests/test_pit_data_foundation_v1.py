from __future__ import annotations

import inspect

from backend.nexus_demo_execution.geometry_contracts import CandidateEvidence
from backend.nexus_demo_execution.historical_market_data import (
    Candle,
    build_dataset,
    interval_ms,
    parse_kline_rows,
)
from backend.nexus_demo_execution.market_structure import (
    build_geometry_inputs_from_klines,
    parse_bybit_kline_list,
)
from backend.nexus_demo_execution.pit_data_foundation import (
    CANONICAL_TIMESTAMP_UNIT,
    CANONICAL_TIMEZONE,
    CURRENT_LIQUIDITY_CLAIMED_AS_ORDERBOOK,
    QUALIFICATION_FEE_SOURCE,
    STRUCTURAL_LIQUIDITY_LABEL,
    FundingRecord,
    fee_policy_for_qualification,
    funding_records_for_decision,
    metadata_status_for_historical_replay,
    realized_funding_cost,
    slippage_policy_for_replay,
    spread_policy_for_replay,
    survivorship_bias_guard,
    validate_candidate_field_asof,
    validate_closed_bar_decision,
    validate_outcome_after_decision,
)
from backend.nexus_demo_execution.session_limits import MIN_NET_REWARD_RISK_RATIO, MIN_NET_REWARD_TO_COST


def _c(ts: int, *, interval: str = "15", price: float = 100.0) -> Candle:
    return Candle(
        ts_ms=ts,
        close_ts_ms=ts + interval_ms(interval),
        open=price,
        high=price + 2.0,
        low=price - 2.0,
        close=price + 0.5,
        volume=10.0,
        turnover=1000.0,
    )


def test_bybit_newest_first_parsing_preserves_start_timestamp_and_order() -> None:
    raw = [
        ["1700000900000", "102", "103", "101", "102.5", "2", "205"],
        ["1700000000000", "100", "101", "99", "100.5", "1", "100"],
    ]

    live_rows = parse_bybit_kline_list(raw)
    historical_rows = parse_kline_rows(raw, interval="15", retrieved_at_ms=1700001000000)

    assert [int(r["open_ts_ms"]) for r in live_rows] == [1700000000000, 1700000900000]
    assert [c.open_ts_ms for c in historical_rows] == [1700000000000, 1700000900000]
    assert historical_rows[0].close_ts_ms == 1700000000000 + interval_ms("15")
    assert historical_rows[0].turnover == 100.0


def test_interval_conversion_exact_close_timestamps() -> None:
    assert interval_ms("1") == 60_000
    assert interval_ms("5") == 300_000
    assert interval_ms("15") == 900_000
    assert interval_ms("30") == 1_800_000
    assert interval_ms("60") == 3_600_000
    assert interval_ms("240") == 14_400_000
    assert interval_ms("D") == 86_400_000


def test_duplicate_and_gap_detection_are_visible_in_manifest() -> None:
    dup = build_dataset(symbol="BTCUSDT", interval="15", candles=[_c(0), _c(0), _c(900_000)])
    gap = build_dataset(symbol="BTCUSDT", interval="15", candles=[_c(0), _c(2_700_000)])

    assert dup.duplicate_interval_count == 1
    assert dup.classification == "DATA_INVALID"
    assert dup.data_quality_status == "INVALID_SAMPLE"
    assert gap.missing_interval_count == 2
    assert gap.data_quality_status == "PIT_GAPS_PRESENT"
    assert gap.manifest()["gap_count"] == 1


def test_invalid_ohlc_and_non_monotonic_timestamp_rejected() -> None:
    invalid = Candle(ts_ms=0, open=105, high=101, low=99, close=100, volume=1)
    invalid_ds = build_dataset(symbol="BTCUSDT", interval="15", candles=[invalid])
    non_mono = build_dataset(symbol="BTCUSDT", interval="15", candles=[_c(900_000), _c(0)])

    assert invalid_ds.classification == "DATA_INVALID"
    assert invalid_ds.data_quality_status == "INVALID_SAMPLE"
    assert non_mono.timestamps_monotonic is False
    assert non_mono.classification == "DATA_INVALID"


def test_partial_future_feature_bar_rejected_and_closed_bar_accepted() -> None:
    bars = [_c(0), _c(900_000)]
    decision = bars[-1].close_ts_ms
    assert decision is not None

    accepted = validate_closed_bar_decision(decision_ts_ms=decision, feature_bars=bars, interval="15")
    rejected = validate_closed_bar_decision(decision_ts_ms=decision - 1, feature_bars=bars, interval="15")

    assert accepted.ok is True
    assert rejected.ok is False
    assert rejected.reason == "partial_or_future_feature_bar"


def test_candidate_field_asof_rejects_future_and_accepts_past() -> None:
    good = CandidateEvidence(
        symbol="BTCUSDT",
        side="Buy",
        entry_price=100.0,
        decision_ts_ms=1000,
        field_asof_ts_ms={"atr": 1000, "support": 900},
    )
    bad = CandidateEvidence(
        symbol="BTCUSDT",
        side="Buy",
        entry_price=100.0,
        decision_ts_ms=1000,
        field_asof_ts_ms={"atr": 1001},
    )

    assert validate_candidate_field_asof(good).ok is True
    assert validate_candidate_field_asof(bad).ok is False
    assert validate_candidate_field_asof(bad).reason == "future_feature_asof_ts"


def test_outcome_candle_before_decision_rejected_next_legal_accepted() -> None:
    accepted = validate_outcome_after_decision(decision_ts_ms=900_000, outcome_bars=[_c(900_000)], interval="15")
    rejected = validate_outcome_after_decision(decision_ts_ms=900_000, outcome_bars=[_c(0)], interval="15")

    assert accepted.ok is True
    assert rejected.ok is False
    assert rejected.reason == "lookahead_outcome_candle"


def test_funding_decision_context_and_realized_crossing_rule() -> None:
    records = [
        FundingRecord(symbol="BTCUSDT", funding_rate=0.001, funding_ts_ms=900_000),
        FundingRecord(symbol="BTCUSDT", funding_rate=0.002, funding_ts_ms=1_800_000),
    ]

    selected, status = funding_records_for_decision(records, decision_ts_ms=1_000_000)
    none_selected, future_only = funding_records_for_decision(records[1:], decision_ts_ms=1_000_000)
    cost = realized_funding_cost(notional=1000.0, entry_ts_ms=800_000, exit_ts_ms=1_000_000, records=records)

    assert status.ok is True
    assert selected is not None and selected.funding_ts_ms == 900_000
    assert none_selected is None
    assert future_only.ok is False
    assert future_only.reason == "future_funding_leakage_rejected"
    assert cost == 1.0


def test_metadata_liquidity_spread_slippage_and_fee_policies_are_honest() -> None:
    assert metadata_status_for_historical_replay(has_pit_history=False) == "CURRENT_ONLY_METADATA"
    assert survivorship_bias_guard(symbol_status_pit_proven=False)["SURVIVORSHIP_BIAS_RISK"] == "HIGH"
    assert STRUCTURAL_LIQUIDITY_LABEL == "STRUCTURAL_LIQUIDITY_PROXY"
    assert CURRENT_LIQUIDITY_CLAIMED_AS_ORDERBOOK is False
    assert spread_policy_for_replay(historical_bid_ask_available=False)["performance_dependent_selection"] is False
    assert spread_policy_for_replay(historical_bid_ask_available=False)["source"] == "FIXED_CONSERVATIVE_BPS_BY_LIQUIDITY_TIER"
    assert slippage_policy_for_replay()["performance_dependent_selection"] is False
    fee = fee_policy_for_qualification()
    assert fee["source"] == QUALIFICATION_FEE_SOURCE
    assert fee["cost_thresholds_changed"] is False
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert MIN_NET_REWARD_TO_COST == 1.5


def test_market_structure_ohlc_calculations_unchanged_with_timestamp_metadata() -> None:
    raw = [
        [str(i * 900_000), str(100 + i), str(102 + i), str(99 + i), str(101 + i), "10", "1000"]
        for i in range(21)
    ]
    rows_without_timestamp = [
        {"open": float(100 + i), "high": float(102 + i), "low": float(99 + i), "close": float(101 + i), "volume": 10.0}
        for i in range(21)
    ]
    rows_with_timestamp = parse_bybit_kline_list(list(reversed(raw)))

    a = build_geometry_inputs_from_klines(last_price=121.0, klines=rows_without_timestamp)
    b = build_geometry_inputs_from_klines(last_price=121.0, klines=rows_with_timestamp)

    assert a["atr"] == b["atr"]
    assert a["recent_swing_high"] == b["recent_swing_high"]
    assert a["recent_swing_low"] == b["recent_swing_low"]
    assert a["support"] == b["support"]
    assert a["resistance"] == b["resistance"]


def test_manifest_contract_fields_and_timestamp_constants() -> None:
    ds = build_dataset(symbol="ETHUSDT", interval="15", candles=[_c(0), _c(900_000)])
    manifest = ds.manifest()

    assert CANONICAL_TIMESTAMP_UNIT == "milliseconds"
    assert CANONICAL_TIMEZONE == "UTC"
    assert manifest["schema_version"] == "pit_historical_dataset_v1"
    assert manifest["dataset_id"]
    assert manifest["earliest_open_ts_ms"] == 0
    assert manifest["latest_close_ts_ms"] == 1_800_000
    assert manifest["record_count"] == 2
    assert manifest["duplicate_count"] == 0
    assert manifest["data_quality_status"] == "PIT_COMPLETE"
    assert manifest["content_sha256"]


def test_offline_foundation_has_no_order_or_network_write_path() -> None:
    import backend.nexus_demo_execution.historical_market_data as hmd
    import backend.nexus_demo_execution.pit_data_foundation as pit

    pit_source = inspect.getsource(pit)
    assert "create_market_order" not in pit_source
    assert "POST" not in pit_source
    assert "PUT" not in pit_source
    assert "PATCH" not in pit_source
    assert "DELETE" not in pit_source
    assert "urlopen" not in pit_source

    http_get_source = inspect.getsource(hmd._http_get)
    assert "Request(" in http_get_source
    assert "method=" not in http_get_source
