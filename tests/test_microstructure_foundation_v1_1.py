"""Tests for Microstructure V1.1 integrity hardening."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_microstructure.collector_v11 import source_semantics_mapping
from backend.nexus_microstructure.integrity import BoundedDedup, SymbolOrderingTracker
from backend.nexus_microstructure.storage_v11 import StreamingPartitionWriter


def test_ordering_scoped_by_symbol_not_cross_symbol():
    t = SymbolOrderingTracker()
    t.observe(exchange="BYBIT", family="AGGRESSIVE_TRADE_FLOW", symbol="BTCUSDT", topic="t", exchange_ts=2000)
    t.observe(exchange="BYBIT", family="AGGRESSIVE_TRADE_FLOW", symbol="ETHUSDT", topic="t", exchange_ts=1000)
    # Interleaved lower ETH ts must NOT count as out-of-order vs BTC
    assert t.session_out_of_order_count == 0
    t.observe(exchange="BYBIT", family="AGGRESSIVE_TRADE_FLOW", symbol="BTCUSDT", topic="t", exchange_ts=1500)
    assert t.per_symbol_out_of_order_count["BTCUSDT"] == 1
    assert t.session_out_of_order_count == 1
    assert t.report()["sequence_gap_status"] == "UNKNOWN"


def test_streaming_writer_no_full_memory_list_and_checksum(tmp_path: Path):
    w = StreamingPartitionWriter(
        tmp_path,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="t",
        buffer_max_events=5,
        flush_interval_s=0.01,
    )
    assert w.full_records_retained_in_memory is False
    assert w.storage_tree_scanned_per_event is False
    for i in range(20):
        w.accept(
            {
                "exchange_timestamp": 1_700_000_000_000 + i * 1000,
                "receive_wall_timestamp": 1_700_000_000_100 + i * 1000,
                "symbol": "BTCUSDT",
                "i": i,
            }
        )
    rep = w.close()
    assert rep["checksum_replay_verified"] is True
    assert rep["partition_count"] >= 1
    assert not hasattr(w, "records") or not getattr(w, "records", None)


def test_bounded_dedup():
    d = BoundedDedup(max_keys=100, window_ms=60_000)
    assert d.seen("a", 1000) is False
    assert d.seen("a", 1001) is True
    assert d.duplicate_count == 1


def test_aggressor_semantics_verified_from_docs():
    s = source_semantics_mapping()
    assert s["aggressor_side_semantics_status"] == "AGGRESSOR_SIDE_SEMANTICS_VERIFIED"
    assert any(m["source_field"] == "S" and m["mapping_status"] == "VERIFIED" for m in s["mappings"])


def test_hard_bans_unchanged():
    assert os.environ["EXCHANGE_WRITE"] == "false"
    assert os.environ["MAINNET"] == "false"
    assert os.environ["REAL_MONEY"] == "false"
