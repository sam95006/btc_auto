"""Collector Cutover V2 — synthetic + read-only public-data-shaped proofs."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["DEMO"] = "false"

import pytest

from backend.nexus_microstructure.collector_cutover_v2 import (
    EVENT_STUDY_STATUS,
    R2_HIGH_DISPOSITIONS,
    RETAINED_CLASSIFICATION_COUNTS,
    CollectorCutoverControllerV2,
    DurablePartitionWriterV2,
    OpenPartitionMigrationBlocked,
    assert_migration_safe,
    open_tail_seal_policy,
)
from backend.nexus_microstructure.collector_cutover_v2.clock_guard import (
    ClockRollbackRejected,
    PersistentClockGuard,
)
from backend.nexus_microstructure.event_study_hard_block_v11_1 import event_study_gate
from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import PartitionIdentityConflict

REPO = Path(__file__).resolve().parents[1]
PUBLIC_FIXTURE = REPO / "tests" / "fixtures" / "collector_cutover_v2" / "public_readonly_ticks.json"


def _tick(symbol: str, ts: int, seq: int) -> dict:
    return {
        "source": "public_readonly_fixture",
        "family": "AGGRESSIVE_TRADE_FLOW",
        "symbol": symbol,
        "exchange_timestamp": ts,
        "receive_wall_timestamp": ts + 1,
        "seq": seq,
        "price": "1",
        "size": "1",
    }


def test_retained_classifications_frozen():
    assert RETAINED_CLASSIFICATION_COUNTS["ACTUAL_DATA_CORRUPTION"] == 0
    assert RETAINED_CLASSIFICATION_COUNTS["EXPECTED_OPEN_TAIL"] == 113
    assert RETAINED_CLASSIFICATION_COUNTS["MANIFEST_BUG"] == 43


def test_event_study_remains_not_ready():
    gate = event_study_gate()
    assert gate["event_study"] == "NOT_READY"
    assert gate["raw_modified"] is False
    assert EVENT_STUDY_STATUS == "NOT_READY"


def test_r2_d003_d005_fixed_not_silent():
    assert R2_HIGH_DISPOSITIONS["R2-D-003"] == "FIXED"
    assert R2_HIGH_DISPOSITIONS["R2-D-005"] == "FIXED"
    assert R2_HIGH_DISPOSITIONS["R2-C-003"] == "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK"


def test_exclusive_partition_ids(tmp_path: Path):
    w1 = DurablePartitionWriterV2(
        tmp_path,
        exchange="PUBLIC",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="t_excl",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    w2 = DurablePartitionWriterV2(
        tmp_path,
        exchange="PUBLIC",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="t_excl",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    base = 1_754_265_600_000
    w1.accept(_tick("BTCUSDT", base, 1))
    with pytest.raises(PartitionIdentityConflict):
        w2.accept(_tick("BTCUSDT", base + 1, 2))
    w1.close()


def test_persistent_clock_guard_survives_reopen(tmp_path: Path):
    meta = tmp_path / "meta"
    g1 = PersistentClockGuard(meta, capture_session_id="clk")
    g1.accept(1_754_265_600_000 + 3_600_000)
    g2 = PersistentClockGuard(meta, capture_session_id="clk")
    with pytest.raises(ClockRollbackRejected):
        g2.accept(1_754_265_600_000)
    g2.arm_resume_boundary()
    assert g2.accept(1_754_265_600_000 + 1000)


def test_migration_refuses_open_partitions(tmp_path: Path):
    w = DurablePartitionWriterV2(
        tmp_path,
        exchange="PUBLIC",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="mig",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    w.accept(_tick("BTCUSDT", 1_754_265_600_000, 1))
    w.abandon_open_without_finalize()
    with pytest.raises(OpenPartitionMigrationBlocked):
        assert_migration_safe(tmp_path)


def test_atomic_seal_clears_open_marker(tmp_path: Path):
    w = DurablePartitionWriterV2(
        tmp_path,
        exchange="PUBLIC",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="ETHUSDT",
        capture_session_id="seal",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    for i in range(3):
        w.accept(_tick("ETHUSDT", 1_754_265_600_000 + i * 1000, i))
    report = w.close()
    assert report["manifest_complete"] is True
    assert report["atomic_manifest_seal"] is True
    assert list(tmp_path.rglob("*.jsonl.gz.open")) == []
    assert list(tmp_path.rglob("*.manifest.json"))


def test_open_tail_seal_policy_does_not_mutate_prior():
    pol = open_tail_seal_policy()
    assert pol["prior_campaign_raw_modified"] is False
    assert pol["prior_expected_open_tail_count"] == 113
    assert pol["event_study"] == "NOT_READY"


def test_public_readonly_fixture_and_controller(tmp_path: Path):
    assert PUBLIC_FIXTURE.is_file()
    ticks = json.loads(PUBLIC_FIXTURE.read_text(encoding="utf-8"))
    assert ticks["read_only"] is True
    assert ticks["exchange_write"] is False
    assert ticks["source"] == "public_market_data_shape_fixture"
    # Feed fixture ticks through cutover writer (no live network).
    root = tmp_path / "public"
    w = DurablePartitionWriterV2(
        root,
        exchange="PUBLIC",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="pub_ro",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    for i, row in enumerate(ticks["ticks"]):
        w.accept(
            {
                "source": ticks["source"],
                "family": "AGGRESSIVE_TRADE_FLOW",
                "symbol": row["symbol"],
                "exchange_timestamp": row["exchange_timestamp"],
                "receive_wall_timestamp": row["exchange_timestamp"] + 1,
                "seq": i,
                "price": row["price"],
                "size": row["size"],
            }
        )
    closed = w.close()
    assert closed["graceful_stop"] is True

    ctl = CollectorCutoverControllerV2(REPO, work_root=tmp_path / "proofs")
    result = ctl.run_synthetic_proofs()
    assert result["all_passed"] is True
    assert result["event_study_readiness_status"] == "NOT_READY"
    assert result["retained_classifications"]["raw_modified"] is False
    assert result["retained_classifications"]["classification_counts"]["ACTUAL_DATA_CORRUPTION"] == 0
    assert result["retained_classifications"]["classification_counts"]["EXPECTED_OPEN_TAIL"] == 113
    assert result["scenarios"]["persistent_clock_guard"]["status"] == "FIXED"
    assert result["scenarios"]["migration_open_partition_guard"]["status"] == "FIXED"
    assert result["demo_used"] is False
    assert result["mainnet_used"] is False
