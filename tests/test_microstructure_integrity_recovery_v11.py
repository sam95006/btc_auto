"""Tests for V11 microstructure integrity recovery."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_microstructure.integrity_recovery_v11.classify import (
    classify_campaign_partitions,
    discover_partitions_v11,
)
from backend.nexus_microstructure.integrity_recovery_v11.linkage import (
    audit_linkage_v11,
    legacy_style_linkage_for_contrast,
)
from backend.nexus_microstructure.integrity_recovery_v11.orchestrator import run_integrity_recovery
from backend.nexus_microstructure.integrity_recovery_v11.synthetic import (
    run_24h_synthetic_logical_capture,
    write_sanitized_checksum_mismatch_fixture,
    write_sanitized_linkage_semantics_fixture,
    write_sanitized_manifest_bug_fixture,
    write_sanitized_open_tail_fixture,
)
from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import (
    DurablePartitionWriterV11,
    manifest_path_for,
    open_marker_for,
)


def _evt(symbol: str, ts: int, seq: int, family: str = "AGGRESSIVE_TRADE_FLOW") -> dict:
    return {
        "family": family,
        "symbol": symbol,
        "exchange_timestamp": ts,
        "receive_wall_timestamp": ts + 1,
        "seq": seq,
        "price": "1",
        "size": "1",
    }


def test_graceful_stop_finalizes_manifest_and_checksum(tmp_path: Path) -> None:
    w = DurablePartitionWriterV11(
        tmp_path,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="ms12_T_GRACE",
        flush_interval_s=0.01,
        buffer_max_events=1,
    )
    base = 1_720_000_000_000
    for i in range(8):
        w.accept(_evt("BTCUSDT", base + i * 1000, i))
    report = w.close()
    assert report["graceful_stop"] is True
    assert report["checksum_replay_verified"] is True
    assert report["manifest_complete"] is True
    p = Path(report["partitions"][0]["path"])
    assert manifest_path_for(p).is_file()
    assert not open_marker_for(p).exists()


def test_process_kill_leaves_open_tail(tmp_path: Path) -> None:
    w = DurablePartitionWriterV11(
        tmp_path,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="ms12_T_KILL",
        flush_interval_s=0.01,
        buffer_max_events=1,
    )
    base = 1_720_000_000_000
    for i in range(12):
        w.accept(_evt("BTCUSDT", base + i * 1000, i))
    abandoned = w.abandon_open_without_finalize()
    assert abandoned is not None
    assert open_marker_for(abandoned).is_file()
    assert not manifest_path_for(abandoned).exists()
    parts = discover_partitions_v11(tmp_path)
    assert len(parts) == 1
    assert parts[0]["is_open_tail"] is True
    assert parts[0]["truncated_tail"] is True
    clf = classify_campaign_partitions(parts)
    assert clf["classification_counts"]["EXPECTED_OPEN_TAIL"] >= 1


def test_partition_rotation_preserves_previous_link(tmp_path: Path) -> None:
    w = DurablePartitionWriterV11(
        tmp_path,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="ms12_T_ROT",
        max_partition_bytes=200,
        flush_interval_s=0.01,
        buffer_max_events=1,
    )
    # Two distinct UTC hours → rotation
    t0 = 1_754_265_600_000  # 2026-08-04 00:00 UTC
    t1 = t0 + 3_600_000  # next hour
    for i in range(5):
        w.accept(_evt("BTCUSDT", t0 + i * 1000, i))
    for i in range(5):
        w.accept(_evt("BTCUSDT", t1 + i * 1000, 100 + i))
    report = w.close()
    assert report["partition_count"] >= 2
    parts = report["partitions"]
    assert parts[0]["previous_partition_id"] is None
    assert parts[1]["previous_partition_id"] == parts[0]["partition_id"]
    discovered = discover_partitions_v11(tmp_path)
    link = audit_linkage_v11(discovered)
    assert link["cross_partition_linkage_status"] == "PASS"


def test_checksum_replay_detects_mismatch(tmp_path: Path) -> None:
    info = write_sanitized_checksum_mismatch_fixture(tmp_path)
    parts = discover_partitions_v11(tmp_path)
    assert any(p["integrity_status"] == "CHECKSUM_MISMATCH" for p in parts)
    clf = classify_campaign_partitions(parts)
    assert clf["classification_counts"]["ACTUAL_DATA_CORRUPTION"] >= 1
    assert "ACTUAL_DATA_CORRUPTION" in info["class"]


def test_linkage_semantics_v1_false_positive_vs_v11(tmp_path: Path) -> None:
    info = write_sanitized_linkage_semantics_fixture(tmp_path)
    root = Path(info["partitions_root"])
    parts = discover_partitions_v11(root)
    # V1-style null identity collapse
    legacy_view = [
        {
            "partition_id": p["partition_id"],
            "capture_session_id": None,
            "family": None,
            "symbol": None,
            "UTC_hour": None,
            "previous_partition_id": None,
        }
        for p in parts
    ]
    legacy = legacy_style_linkage_for_contrast(legacy_view)
    fixed = audit_linkage_v11(parts)
    assert legacy["linkage_breaks"] >= 1
    assert fixed["linkage_breaks"] == 0


def test_manifest_bug_fixture(tmp_path: Path) -> None:
    write_sanitized_manifest_bug_fixture(tmp_path)
    parts = discover_partitions_v11(tmp_path)
    assert any(p["integrity_status"] == "OK" and not p["manifest_present"] for p in parts)
    clf = classify_campaign_partitions(parts)
    assert clf["classification_counts"]["MANIFEST_BUG"] >= 1


def test_restart_resume_new_chain_after_open_tail(tmp_path: Path) -> None:
    """Kill leaves open tail; resume with new writer starts fresh chain (claimed null OK)."""
    session = "ms12_T_RESUME"
    w1 = DurablePartitionWriterV11(
        tmp_path,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id=session,
        flush_interval_s=0.01,
        buffer_max_events=1,
    )
    base = 1_754_265_600_000
    for i in range(6):
        w1.accept(_evt("BTCUSDT", base + i * 1000, i))
    w1.abandon_open_without_finalize()

    w2 = DurablePartitionWriterV11(
        tmp_path,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id=session,
        flush_interval_s=0.01,
        buffer_max_events=1,
    )
    # Next hour after resume
    for i in range(6):
        w2.accept(_evt("BTCUSDT", base + 3_600_000 + i * 1000, 100 + i))
    w2.close()

    parts = discover_partitions_v11(tmp_path)
    assert sum(1 for p in parts if p["is_open_tail"]) == 1
    assert sum(1 for p in parts if p["manifest_present"]) >= 1
    link = audit_linkage_v11(parts)
    assert link["cross_partition_linkage_status"] == "PASS"


def test_24h_synthetic_logical_capture(tmp_path: Path) -> None:
    result = run_24h_synthetic_logical_capture(tmp_path, hours=24, events_per_hour=2)
    assert result["hours"] == 24
    assert result["graceful_stop"] is True
    assert result["checksum_replay_verified"] is True
    assert result["partition_count"] >= 24  # at least one hour bucket per symbol-hour
    parts = discover_partitions_v11(tmp_path)
    link = audit_linkage_v11(parts)
    assert link["cross_partition_linkage_status"] == "PASS"
    assert all(not p["is_open_tail"] for p in parts)


def test_open_tail_fixture_classification(tmp_path: Path) -> None:
    write_sanitized_open_tail_fixture(tmp_path)
    parts = discover_partitions_v11(tmp_path)
    clf = classify_campaign_partitions(
        parts,
        legacy_checksum_ids={parts[0]["partition_id"]},
        legacy_linkage_ids={parts[0]["partition_id"]},
    )
    counts = clf["classification_counts"]
    assert counts["EXPECTED_OPEN_TAIL"] >= 1
    assert counts["FINALIZER_FALSE_POSITIVE"] >= 1
    assert counts["LINKAGE_SEMANTICS_BUG"] >= 1


def test_recovery_runner_on_fixtures(tmp_path: Path) -> None:
    # Build a mini campaign with mixed issues
    write_sanitized_open_tail_fixture(tmp_path / "camp")
    write_sanitized_manifest_bug_fixture(tmp_path / "camp")
    out = tmp_path / "artifacts"
    fixtures = tmp_path / "fixtures"
    result = run_integrity_recovery(
        partitions_root=tmp_path / "camp",
        output_dir=out,
        fixtures_dir=fixtures,
        write_fixtures=True,
        campaign_id="fixture_campaign",
    )
    assert result["status"]["event_study_readiness_status"] == "NOT_READY"
    assert result["status"]["raw_bytes_modified"] is False
    assert (out / "recovery_map.json").is_file()
    assert (out / "forensic_rca.json").is_file()
    rm = json.loads((out / "recovery_map.json").read_text(encoding="utf-8"))
    assert rm["original_hashes_preserved"] is True
    assert rm["silent_repair_executed"] is False
    assert (fixtures / "fixture_index.json").is_file()
