"""R2-CD critical remediation — two-pass negative proofs (Cursor-native).

Hard bans: no raw campaign mutation under .nexus_runtime/microstructure;
Event Study remains NOT_READY; no silent repair; no READY claim.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.nexus_microstructure.integrity_recovery_v11.classify import (
    classify_campaign_partitions,
    discover_partitions_v11,
)
from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import (
    DurablePartitionWriterV11,
    PartitionIdentityConflict,
    manifest_path_for,
    open_marker_for,
)
from backend.nexus_recovery.dr_v2.recovery import DisasterRecoveryV2
from backend.nexus_runtime.durability_v2.constants import (
    BLOCKED_AMBIGUOUS_STATE,
    CORRUPTION_DETECTED,
    SNAPSHOT_OK,
)
from backend.nexus_runtime.durability_v2.engine import RuntimeDurabilityV2
from backend.nexus_runtime.durability_v2.faults import inject_payload_bit_corruption
from backend.nexus_runtime.durability_v2.ledger import DurableEventLedgerV2


def _evt(symbol: str, ts: int, seq: int) -> dict:
    return {
        "family": "AGGRESSIVE_TRADE_FLOW",
        "symbol": symbol,
        "exchange_timestamp": ts,
        "receive_wall_timestamp": ts + 1,
        "seq": seq,
        "price": "1",
        "size": "1",
    }


def _run_pass(tmp_path: Path, pass_id: str) -> dict:
    """Execute all critical negative proofs once; return structured matrix row."""
    results: dict = {"pass_id": pass_id, "scenarios": {}}

    # --- R2-C-001: payload bit-flip must not SNAPSHOT_OK / advance LKG ---
    root_c1 = tmp_path / pass_id / "c001"
    dur = RuntimeDurabilityV2(root_c1)
    led = dur.open_ledger()
    led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="r2fix",
        payload={"n": 1},
        idempotency_key="pay-1",
    )
    inject_payload_bit_corruption(led, seq=1)
    det = dur.detect_corruption(led)
    gen_before = dur._generation
    lkg_before = dur.lkg_path.exists()
    snap = dur.create_snapshot(led)
    led.close()
    c001_ok = (
        det.get("corruption_detection_status") == CORRUPTION_DETECTED
        and snap.status == CORRUPTION_DETECTED
        and dur._generation == gen_before
        and dur.lkg_path.exists() == lkg_before
    )
    results["scenarios"]["R2-C-001"] = {
        "status": "FIXED" if c001_ok else "REMAINING",
        "detect": det.get("corruption_detection_status"),
        "snapshot_status": snap.status,
        "generation_advanced": dur._generation != gen_before,
        "lkg_advanced": dur.lkg_path.exists() and not lkg_before,
    }

    # --- R2-C-002: position from checksummed bytes; wal divergence blocks ---
    root_c2 = tmp_path / pass_id / "c002"
    dur2 = RuntimeDurabilityV2(root_c2)
    led2 = dur2.open_ledger()
    for i in range(5):
        led2.append(
            aggregate_id=f"a{i}",
            aggregate_type="DECISION",
            event_type="X",
            source="r2fix",
            payload={"i": i},
            idempotency_key=f"k{i}",
        )
    orig = DurableEventLedgerV2.event_count
    fired = {"n": 0}

    def patched(self: DurableEventLedgerV2) -> int:
        fired["n"] += 1
        if fired["n"] == 1:
            self.append(
                aggregate_id="late",
                aggregate_type="DECISION",
                event_type="X",
                source="r2fix",
                payload={"late": True},
                idempotency_key="late",
            )
        return orig(self)

    DurableEventLedgerV2.event_count = patched  # type: ignore[method-assign]
    try:
        snap2 = dur2.create_snapshot(led2)
    finally:
        DurableEventLedgerV2.event_count = orig  # type: ignore[method-assign]

    assert snap2.status == SNAPSHOT_OK
    snap_path = Path(snap2.detail["snapshot_path"])
    conn = sqlite3.connect(str(snap_path))
    try:
        file_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()
    claimed = int(snap2.detail["source_ledger_position"])
    position_ok = claimed == file_count and snap2.detail.get("position_source") == "checksummed_main_file"

    # Companion -wal divergence must block restore (not silent drop).
    wal_path = Path(str(snap_path) + "-wal")
    shm_path = Path(str(snap_path) + "-shm")
    # Ensure no leftover handles from the count probe.
    for p in (wal_path, shm_path):
        try:
            p.unlink(missing_ok=True)
        except PermissionError:
            pass
    wal_path.write_bytes(b"\x00" * 64)
    restored_blocked = dur2.restore_last_known_good(allow_ambiguous=False)
    wal_block_ok = restored_blocked.status == BLOCKED_AMBIGUOUS_STATE and (
        restored_blocked.detail.get("reason") == "snapshot_companion_wal_divergence"
    )
    led2.close()
    for p in (wal_path, shm_path):
        try:
            p.unlink(missing_ok=True)
        except PermissionError:
            pass
    c002_ok = position_ok and wal_block_ok
    results["scenarios"]["R2-C-002"] = {
        "status": "FIXED" if c002_ok else "REMAINING",
        "claimed": claimed,
        "file_count": file_count,
        "position_ok": position_ok,
        "wal_restore_status": restored_blocked.status,
        "wal_block_ok": wal_block_ok,
    }

    # --- R2-D-001: exclusive create / identity conflict ---
    root_d1 = tmp_path / pass_id / "d001"
    base = 1_754_265_600_000
    w1 = DurablePartitionWriterV11(
        root_d1,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="r2_dup",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    w2 = DurablePartitionWriterV11(
        root_d1,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="r2_dup",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    w1.accept(_evt("BTCUSDT", base, 1))
    conflicted = False
    try:
        w2.accept(_evt("BTCUSDT", base + 1, 2))
    except PartitionIdentityConflict:
        conflicted = True
    w1.close()
    try:
        w2.close()
    except Exception:
        pass
    gz_files = list(root_d1.rglob("*.jsonl.gz"))
    d001_ok = conflicted and len(gz_files) == 1
    results["scenarios"]["R2-D-001"] = {
        "status": "FIXED" if d001_ok else "REMAINING",
        "conflict_raised": conflicted,
        "gz_file_count": len(gz_files),
    }

    # --- R2-C-005: unbound checkpoint rejected ---
    root_c5 = tmp_path / pass_id / "c005"
    dr = DisasterRecoveryV2(root_c5)
    premature = {
        "checkpoint_id": "premature-before-fsync",
        "ledger_position": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "note": "written without snapshot/LKG",
    }
    dr.durability.checkpoint_path.write_text(json.dumps(premature, indent=2) + "\n", encoding="utf-8")
    seal = dr.durability.validate_checkpoint_seal()
    recovered = dr.recover()
    c005_ok = (
        seal.get("reason") == "checkpoint_unbound_missing_lkg_seal"
        and recovered.get("status") == BLOCKED_AMBIGUOUS_STATE
    )
    # Sealed path after real snapshot
    led5 = dr.durability.open_ledger()
    led5.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="r2fix",
        payload={"n": 1},
        idempotency_key="c5-1",
    )
    assert dr.durability.create_snapshot(led5).status == SNAPSHOT_OK
    led5.close()
    seal_ok = dr.durability.validate_checkpoint_seal().get("status") == "PASS"
    c005_ok = c005_ok and seal_ok
    results["scenarios"]["R2-C-005"] = {
        "status": "FIXED" if c005_ok else "REMAINING",
        "unbound_blocked": recovered.get("status") == BLOCKED_AMBIGUOUS_STATE,
        "sealed_pass": seal_ok,
    }

    # --- R2-D-002: orphan .open after finalize classified ---
    root_d2 = tmp_path / pass_id / "d002"
    w = DurablePartitionWriterV11(
        root_d2,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="r2_orphan",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    for i in range(5):
        w.accept(_evt("BTCUSDT", base + i * 1000, i))
    report = w.close()
    path = Path(report["partitions"][0]["path"])
    open_marker_for(path).write_text(
        json.dumps({"status": "OPEN", "orphaned_after_finalize": True}) + "\n",
        encoding="utf-8",
    )
    parts = discover_partitions_v11(root_d2)
    clf = classify_campaign_partitions(parts)
    d002_ok = (
        parts[0]["manifest_present"]
        and parts[0]["open_marker_present"]
        and clf["classification_counts"].get("FINALIZE_MARKER_ORPHAN", 0) >= 1
    )
    results["scenarios"]["R2-D-002"] = {
        "status": "FIXED" if d002_ok else "REMAINING",
        "classifications": clf["classification_counts"],
        "finding_count": clf["finding_count"],
    }

    # --- R2-D-004: gzip-closed + .open + no manifest → INTERRUPTED_FINALIZE ---
    root_d4 = tmp_path / pass_id / "d004"
    w4 = DurablePartitionWriterV11(
        root_d4,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="ETHUSDT",
        capture_session_id="r2_gz_mid",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    for i in range(6):
        w4.accept(_evt("ETHUSDT", base + i * 1000, i))
    w4.flush()
    path_b = w4._path
    assert path_b is not None and w4._fh is not None
    w4._fh.close()
    w4._fh = None
    parts_b = discover_partitions_v11(root_d4)
    clf_b = classify_campaign_partitions(parts_b)
    d004_ok = (
        open_marker_for(path_b).is_file()
        and not manifest_path_for(path_b).exists()
        and parts_b
        and parts_b[0].get("interrupted_finalize") is True
        and clf_b["classification_counts"].get("INTERRUPTED_FINALIZE", 0) >= 1
    )
    results["scenarios"]["R2-D-004"] = {
        "status": "FIXED" if d004_ok else "REMAINING",
        "interrupted_finalize": parts_b[0].get("interrupted_finalize") if parts_b else None,
        "classifications": clf_b["classification_counts"],
    }

    results["all_critical_fixed"] = all(
        results["scenarios"][k]["status"] == "FIXED"
        for k in ("R2-C-001", "R2-C-002", "R2-D-001")
    )
    results["hardened_fixed"] = all(
        results["scenarios"][k]["status"] == "FIXED"
        for k in ("R2-C-005", "R2-D-002", "R2-D-004")
    )
    return results


def test_r2_cd_remediation_two_pass(tmp_path: Path):
    pass1 = _run_pass(tmp_path, "PASS_1")
    pass2 = _run_pass(tmp_path, "PASS_2")
    assert pass1["all_critical_fixed"] is True
    assert pass2["all_critical_fixed"] is True
    assert pass1["hardened_fixed"] is True
    assert pass2["hardened_fixed"] is True
    # Deterministic two-pass: same FIXED matrix
    for key in ("R2-C-001", "R2-C-002", "R2-D-001", "R2-C-005", "R2-D-002", "R2-D-004"):
        assert pass1["scenarios"][key]["status"] == pass2["scenarios"][key]["status"] == "FIXED"


def test_r2_c001_negative_no_lkg_on_payload_corruption(tmp_path: Path):
    dur = RuntimeDurabilityV2(tmp_path / "d")
    led = dur.open_ledger()
    led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="t",
        payload={"n": 1},
        idempotency_key="k1",
    )
    inject_payload_bit_corruption(led, seq=1)
    snap = dur.create_snapshot(led)
    led.close()
    assert snap.status == CORRUPTION_DETECTED
    assert not dur.lkg_path.exists()
    assert snap.detail.get("payload_hash_mismatch") is True


def test_r2_d001_negative_second_writer_raises(tmp_path: Path):
    w1 = DurablePartitionWriterV11(
        tmp_path,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="dup",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    w2 = DurablePartitionWriterV11(
        tmp_path,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="dup",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    base = 1_754_265_600_000
    w1.accept(_evt("BTCUSDT", base, 1))
    with pytest.raises(PartitionIdentityConflict):
        w2.accept(_evt("BTCUSDT", base + 1, 2))
    w1.close()
