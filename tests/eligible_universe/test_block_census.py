"""Focused tests for V18.2 Phase A block census classifier/export."""
from __future__ import annotations

from backend.nexus_eligible_universe.block_census import (
    PRIMARY_BLOCK_REASONS,
    aggregate_census,
    classify_block_reasons,
)
from backend.nexus_eligible_universe.engine import classify_instrument
from backend.nexus_eligible_universe.models import InstrumentSnapshot

AS_OF = 1_700_000_000_000


def _sparse_live_like(symbol: str = "BTCUSDT") -> InstrumentSnapshot:
    """Mirrors V18.1 cycle path: status/quote/launch present; specs/metrics None."""
    return InstrumentSnapshot(
        symbol=symbol,
        exchange="bybit",
        category="linear",
        status="Trading",
        quote_coin="USDT",
        base_coin="BTC",
        launch_time_ms=AS_OF - 400 * 86_400_000,
        tick_size=None,
        lot_size=None,
        min_notional=None,
        turnover_24h=None,
        trade_count_24h=None,
        spread_bps=None,
        book_depth_usdt=None,
        funding_available=None,
        oi_available=None,
        history_bars=None,
        data_completeness=None,
        data_trust_status=None,
        delisting_flag=None,
        round_trip_cost_bps=None,
        last_price=None,
    )


def test_primary_reason_vocabulary():
    assert "ADAPTER_SCHEMA_ERROR" in PRIMARY_BLOCK_REASONS
    assert "UNKNOWN_REQUIRES_REVIEW" in PRIMARY_BLOCK_REASONS
    assert "VALID_SAFETY_BLOCK" in PRIMARY_BLOCK_REASONS


def test_sparse_catalog_maps_to_adapter_schema_error():
    inst = _sparse_live_like()
    decision = classify_instrument(inst, as_of_ms=AS_OF)
    assert decision.universe_class != "ELIGIBLE"
    row = classify_block_reasons(
        inst,
        decision,
        source_adapter="bybit_official_read_only",
        normalization_status="PARTIAL_V18_1_CYCLE_PATH",
        pit_status="N/A",
        data_class="LIVE_READ_ONLY_CENSUS",
    )
    assert row["primary_block_reason"] in PRIMARY_BLOCK_REASONS
    assert row["primary_block_reason"] == "ADAPTER_SCHEMA_ERROR"
    assert "tick_size" in row["missing_fields"]
    assert "lot_size" in row["missing_fields"]
    assert row["final_universe_status"] != "ELIGIBLE"
    assert len(row["secondary_block_reasons"]) >= 1


def test_aggregate_histogram_and_fault_counts():
    rows = []
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        inst = _sparse_live_like(sym)
        decision = classify_instrument(inst, as_of_ms=AS_OF)
        rows.append(
            classify_block_reasons(
                inst,
                decision,
                source_adapter="test",
                normalization_status="PARTIAL_V18_1_CYCLE_PATH",
                pit_status="N/A",
                data_class="TEST",
            )
        )
    agg = aggregate_census(rows)
    assert agg["contract_count"] == 3
    assert agg["adapter_fault_count"] == 3
    assert agg["unknown_count"] == 0
    assert "ADAPTER_SCHEMA_ERROR" in agg["block_reason_histogram"]
    assert agg["contracts_with_multiple_reasons"] == 3


def test_bybit_trade_count_gap_is_valid_safety_not_schema_error():
    """After specs/metrics wired, missing Bybit trade_count is fail-closed safety."""
    inst = InstrumentSnapshot(
        symbol="BTCUSDT",
        exchange="bybit",
        status="Trading",
        quote_coin="USDT",
        base_coin="BTC",
        launch_time_ms=AS_OF - 400 * 86_400_000,
        tick_size=0.1,
        lot_size=0.001,
        min_notional=5.0,
        turnover_24h=50_000_000,
        trade_count_24h=None,  # Bybit public gap
        spread_bps=1.0,
        book_depth_usdt=100_000,
        funding_available=True,
        oi_available=True,
        open_interest_value=2_000_000,
        history_bars=120,
        data_completeness=0.93,
        data_trust_status="TRUSTED",
        delisting_flag=False,
        round_trip_cost_bps=12.0,
        last_price=60000.0,
    )
    decision = classify_instrument(inst, as_of_ms=AS_OF)
    row = classify_block_reasons(
        inst,
        decision,
        source_adapter="bybit_public_v5",
        normalization_status="OK",
        pit_status="N/A",
        data_class="LIVE_READ_ONLY",
    )
    assert decision.universe_class != "ELIGIBLE"
    assert row["primary_block_reason"] == "VALID_SAFETY_BLOCK"
    assert "ADAPTER_SCHEMA_ERROR" not in [row["primary_block_reason"], *row["secondary_block_reasons"]]


def test_unknown_never_becomes_eligible_in_census_path():
    inst = InstrumentSnapshot(symbol="ZUSDT", status=None)
    decision = classify_instrument(inst, as_of_ms=AS_OF)
    row = classify_block_reasons(
        inst,
        decision,
        source_adapter="test",
        normalization_status="OK",
        pit_status="N/A",
        data_class="TEST",
    )
    assert decision.universe_class != "ELIGIBLE"
    assert row["final_universe_status"] != "ELIGIBLE"
    assert row["primary_block_reason"] in PRIMARY_BLOCK_REASONS
