"""Tests for Microstructure Data Foundation V1."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_microstructure import data_contracts
from backend.nexus_microstructure.derived_bars import validate_derived_bars
from backend.nexus_microstructure.storage import PartitionWriter, event_checksum


def test_contracts_forbid_strategy_and_write():
    c = data_contracts()
    assert c["authenticated_exchange_write_client"] is False
    assert c["new_strategy_generation_allowed"] is False
    assert c["backtest_allowed"] is False
    assert "aggressor_side" not in str(c).lower() or "UNKNOWN" in c["aggressor_side_rule"]


def test_duplicate_rejection_and_checksum(tmp_path: Path):
    w = PartitionWriter(tmp_path, family="AGGRESSIVE_TRADE_FLOW", capture_session_id="t1", storage_cap_bytes=10_000_000)
    ev = {
        "sequence_or_dedup_key": "k1",
        "exchange_timestamp": 1000,
        "receive_timestamp": 1001,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "notional": 1.0,
        "quantity": 1.0,
    }
    assert w.accept(ev) is True
    assert w.accept(ev) is False
    assert w.duplicate_count == 1
    # out of order
    assert w.accept({**ev, "sequence_or_dedup_key": "k2", "exchange_timestamp": 900}) is True
    assert w.out_of_order_count == 1
    report = w.close()
    assert report["checksum_reproducible"] is True
    assert event_checksum(w.records) == report["checksum"]


def test_storage_cap_enforced(tmp_path: Path):
    w = PartitionWriter(tmp_path, family="LIQUIDATION_EVENTS", capture_session_id="cap", storage_cap_bytes=200)
    accepted = 0
    for i in range(50):
        ok = w.accept(
            {
                "sequence_or_dedup_key": f"k{i}",
                "exchange_timestamp": 1000 + i,
                "receive_timestamp": 1000 + i,
                "symbol": "ETHUSDT",
                "liquidation_side": "BUY",
                "notional": 1.0,
                "quantity": 1.0,
                "payload_pad": "x" * 80,
            }
        )
        if ok:
            accepted += 1
        if w.cap_hit:
            break
    report = w.close()
    assert w.cap_hit is True or accepted < 50
    assert report["record_count"] == accepted


def test_derived_bars_retain_checksum_no_signal():
    events = [
        {
            "symbol": "BTCUSDT",
            "exchange_timestamp": 1_700_000_000_000 + i * 100,
            "side": "BUY" if i % 2 == 0 else "SELL",
            "notional": 10.0,
            "quantity": 1.0,
        }
        for i in range(20)
    ]
    out = validate_derived_bars(
        trade_events=events,
        liq_events=[],
        trade_checksum="abc",
        liq_checksum="def",
    )
    assert out["derived_1s_bar_count"] >= 1
    assert out["source_checksum_linkage_status"] == "PASS"
    assert out["signal_generated"] is False
    assert out["strategy_generated"] is False
    assert out["sample_1s_bar"]["source_partition_checksums"] == ["abc"]


def test_smoke_cohort_label_not_production():
    # Contract-level assertion; live fetch covered in integration smoke
    c = data_contracts()
    assert c["exchange_phase1"] == "BYBIT"
    assert os.environ["EXCHANGE_WRITE"] == "false"
