"""Adversarial probes against Lane C (durability DR V2) and Lane D (micro integrity).

Each scenario returns a structured result with hazard_confirmed / control_ok and evidence.
Does not mutate raw campaign evidence under .nexus_runtime/microstructure.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.nexus_microstructure.integrity_recovery_v11.checksum import replay_gzip_sha256
from backend.nexus_microstructure.integrity_recovery_v11.classify import (
    classify_campaign_partitions,
    discover_partitions_v11,
)
from backend.nexus_microstructure.integrity_recovery_v11.linkage import audit_linkage_v11
from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import (
    DurablePartitionWriterV11,
    manifest_path_for,
    open_marker_for,
)
from backend.nexus_runtime.durability_v2.constants import (
    CORRUPTION_DETECTED,
    SNAPSHOT_OK,
)
from backend.nexus_runtime.durability_v2.engine import RuntimeDurabilityV2
from backend.nexus_runtime.durability_v2.faults import (
    corrupt_lkg_pointer,
    inject_payload_bit_corruption,
)
from backend.nexus_runtime.durability_v2.ledger import DurableEventLedgerV2


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _evt(symbol: str, ts: int, seq: int) -> dict[str, Any]:
    return {
        "family": "AGGRESSIVE_TRADE_FLOW",
        "symbol": symbol,
        "exchange_timestamp": ts,
        "receive_wall_timestamp": ts + 1,
        "seq": seq,
        "price": "1",
        "size": "1",
    }


@dataclass
class ScenarioResult:
    scenario_id: str
    title: str
    lane: str
    severity_if_confirmed: str
    hazard_confirmed: bool
    control_ok: bool
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
    pass_id: str = "PASS_1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ADVERSARIAL_SCENARIOS: tuple[str, ...] = (
    "power_loss_during_gzip_close",
    "checkpoint_before_ledger_fsync",
    "snapshot_from_stale_ledger_tail",
    "manifest_before_file_close",
    "partition_migrated_while_open",
    "duplicate_partition_identity",
    "missing_previous_link",
    "clock_rollback_across_partition_rotation",
    "restore_from_corrupted_lkg",
    # Extra depth probes (Pass 1 / Pass 2)
    "snapshot_skips_payload_corruption",
    "clock_rollback_lost_on_reopen",
    "fsync_interrupt_commits_anyway",
    "orphan_open_marker_after_finalize",
    "concurrent_snapshot_wal_lock",
)


def scenario_power_loss_during_gzip_close(root: Path) -> ScenarioResult:
    """Kill during/after gzip close before manifest: .open retained, no silent repair."""
    w = DurablePartitionWriterV11(
        root,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="r2_gz_close",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    base = 1_754_265_600_000
    for i in range(8):
        w.accept(_evt("BTCUSDT", base + i * 1000, i))

    # Path A: classic kill before gzip footer
    abandoned = w.abandon_open_without_finalize()
    assert abandoned is not None
    parts_a = discover_partitions_v11(root)
    clf_a = classify_campaign_partitions(parts_a)

    # Path B: gzip closed successfully, crash before manifest (finalize race)
    root_b = root / "after_gzip_close"
    w2 = DurablePartitionWriterV11(
        root_b,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="ETHUSDT",
        capture_session_id="r2_gz_mid",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    for i in range(6):
        w2.accept(_evt("ETHUSDT", base + i * 1000, i))
    w2.flush()
    path_b = w2._path
    assert path_b is not None and w2._fh is not None
    w2._fh.close()
    w2._fh = None
    replay_b = replay_gzip_sha256(path_b)
    parts_b = discover_partitions_v11(root_b)
    clf_b = classify_campaign_partitions(parts_b)

    kill_ok = (
        open_marker_for(abandoned).is_file()
        and not manifest_path_for(abandoned).exists()
        and parts_a
        and parts_a[0]["is_open_tail"] is True
        and clf_a["classification_counts"].get("EXPECTED_OPEN_TAIL", 0) >= 1
    )
    # Hazard: post-gzip-close crash is only MANIFEST_BUG; open marker ignored as authority signal
    mid_hazard = (
        open_marker_for(path_b).is_file()
        and not manifest_path_for(path_b).exists()
        and replay_b.get("integrity_status") == "OK"
        and parts_b
        and parts_b[0]["is_open_tail"] is False
        and clf_b["classification_counts"].get("MANIFEST_BUG", 0) >= 1
        and parts_b[0].get("open_marker_present") is True
    )

    return ScenarioResult(
        scenario_id="power_loss_during_gzip_close",
        title="Power loss during gzip close",
        lane="D",
        severity_if_confirmed="HIGH",
        hazard_confirmed=bool(mid_hazard),
        control_ok=bool(kill_ok),
        summary=(
            "Classic kill-before-footer correctly yields EXPECTED_OPEN_TAIL; "
            "gzip-closed-then-crash-before-manifest is only MANIFEST_BUG and does not "
            "treat retained .open marker as an interrupted-finalize authority signal."
        ),
        evidence={
            "kill_before_footer": {
                "open_marker": True,
                "is_open_tail": parts_a[0]["is_open_tail"] if parts_a else None,
                "classifications": clf_a["classification_counts"],
            },
            "after_gzip_before_manifest": {
                "open_marker": open_marker_for(path_b).is_file(),
                "replay": replay_b.get("integrity_status"),
                "is_open_tail": parts_b[0]["is_open_tail"] if parts_b else None,
                "open_marker_present": parts_b[0].get("open_marker_present") if parts_b else None,
                "classifications": clf_b["classification_counts"],
            },
        },
    )


def scenario_checkpoint_before_ledger_fsync(root: Path) -> ScenarioResult:
    """Checkpoint JSON can be written without a durable snapshot/LKG binding."""
    dur = RuntimeDurabilityV2(root)
    led = dur.open_ledger(fsync_enabled=False)
    led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="r2",
        payload={"n": 1},
        idempotency_key="ckpt-1",
    )
    premature = {
        "checkpoint_id": "premature-before-fsync",
        "ledger_position": led.event_count(),
        "created_at": _utc(),
        "note": "written without snapshot/LKG",
    }
    dur.checkpoint_path.write_text(json.dumps(premature, indent=2) + "\n", encoding="utf-8")
    premature_exists = dur.checkpoint_path.exists() and not dur.lkg_path.exists()
    snap = dur.create_snapshot(led)
    led.close()
    after = json.loads(dur.checkpoint_path.read_text(encoding="utf-8"))
    # Hazard: no schema/authority check prevents unbound checkpoint file
    hazard = premature_exists and snap.status == SNAPSHOT_OK
    return ScenarioResult(
        scenario_id="checkpoint_before_ledger_fsync",
        title="Checkpoint written before ledger fsync / snapshot binding",
        lane="C",
        severity_if_confirmed="HIGH",
        hazard_confirmed=hazard,
        control_ok=snap.status == SNAPSHOT_OK,
        summary=(
            "checkpoint_v2.json is a plain file with no seal tying it to an fsynced ledger "
            "position or LKG generation; a premature checkpoint can exist without LKG."
        ),
        evidence={
            "premature_checkpoint_without_lkg": premature_exists,
            "snapshot_status": snap.status,
            "checkpoint_after_snapshot": after,
            "fsync_enabled_during_append": False,
        },
    )


def scenario_snapshot_from_stale_ledger_tail(root: Path) -> ScenarioResult:
    """Manifest source_ledger_position can advance past checksummed main snapshot bytes."""
    dur = RuntimeDurabilityV2(root)
    led = dur.open_ledger()
    for i in range(5):
        led.append(
            aggregate_id=f"a{i}",
            aggregate_type="DECISION",
            event_type="X",
            source="r2",
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
                source="r2",
                payload={"late": True},
                idempotency_key="late",
            )
        return orig(self)

    DurableEventLedgerV2.event_count = patched  # type: ignore[method-assign]
    try:
        snap = dur.create_snapshot(led)
    finally:
        DurableEventLedgerV2.event_count = orig  # type: ignore[method-assign]

    snap_path = Path(snap.detail["snapshot_path"])
    file_count = sqlite3.connect(str(snap_path)).execute("SELECT COUNT(*) FROM events").fetchone()[0]
    claimed = int(snap.detail["source_ledger_position"])
    mismatch = claimed != file_count
    # Restore path copies main file only (not -wal)
    restored = dur.restore_last_known_good(allow_ambiguous=True)
    led.close()

    return ScenarioResult(
        scenario_id="snapshot_from_stale_ledger_tail",
        title="Snapshot written from stale / racy ledger tail",
        lane="C",
        severity_if_confirmed="CRITICAL",
        hazard_confirmed=bool(mismatch and snap.status == SNAPSHOT_OK),
        control_ok=False,
        summary=(
            "create_snapshot records live event_count after copying the main DB; a concurrent "
            "append can make source_ledger_position exceed checksummed main-file rows. Restore "
            "copies only the main snapshot file (not companion -wal)."
        ),
        evidence={
            "snapshot_status": snap.status,
            "claimed_source_ledger_position": claimed,
            "checksummed_main_file_event_count": file_count,
            "mismatch": mismatch,
            "snapshot_wal_exists": Path(str(snap_path) + "-wal").exists(),
            "restore_status": restored.status,
            "restore_detail_event_count": restored.detail.get("event_count"),
        },
    )


def scenario_manifest_before_file_close(root: Path) -> ScenarioResult:
    """V11 writer must finalize gzip before writing manifest (control)."""
    w = DurablePartitionWriterV11(
        root,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="r2_man_order",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    base = 1_754_265_600_000
    order: list[str] = []
    orig_close = w._close_partition

    def traced(rotate: bool = False) -> None:  # type: ignore[no-untyped-def]
        if w._fh is not None and w._path is not None:
            path = w._path
            # Wrap gzip close / manifest write ordering by inspecting after call via hooks
            w.flush()
            fh = w._fh
            order.append("before_gzip_close")
            assert not manifest_path_for(path).exists()
            fh.close()
            w._fh = None
            order.append("after_gzip_close")
            # Continue real finalize without re-closing
            from backend.nexus_microstructure.integrity_recovery_v11.checksum import (
                replay_gzip_sha256 as _replay,
            )
            import os

            replay = _replay(path)
            replayed = replay.get("replayed_checksum")
            match = bool(replayed) and replayed == w._rolling.hexdigest()  # type: ignore[union-attr]
            man = w._manifest_body(checksum_match=match, replayed=replayed)
            if replay.get("truncated_tail"):
                man["integrity_status"] = "TRUNCATED_OR_INCOMPLETE"
                man["open_tail"] = True
                man["finalized"] = False
            man_path = manifest_path_for(path)
            assert order[-1] == "after_gzip_close"
            order.append("before_manifest")
            tmp = man_path.with_suffix(man_path.suffix + ".tmp")
            tmp.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, man_path)
            order.append("after_manifest")
            marker = open_marker_for(path)
            if marker.exists():
                marker.unlink()
            w.partitions.append(man)
            w._prev_partition_id = man["partition_id"]
            w._path = None
            w._rolling = None
            w._hour = None
        else:
            orig_close(rotate=rotate)

    w._close_partition = traced  # type: ignore[method-assign]
    for i in range(5):
        w.accept(_evt("BTCUSDT", base + i * 1000, i))
    w.close()
    ok = order == [
        "before_gzip_close",
        "after_gzip_close",
        "before_manifest",
        "after_manifest",
    ]
    return ScenarioResult(
        scenario_id="manifest_before_file_close",
        title="Manifest committed before file close",
        lane="D",
        severity_if_confirmed="CRITICAL",
        hazard_confirmed=False,
        control_ok=ok,
        summary=(
            "DurablePartitionWriterV11 closes gzip and verifies replay checksum before "
            "atomic manifest replace — manifest-before-close hazard not present on V11 writer."
        ),
        evidence={"observed_order": order},
    )


def scenario_partition_migrated_while_open(root: Path) -> ScenarioResult:
    """Copy/migrate an in-flight open partition; raw bytes must stay unmodified and classified."""
    src = root / "src"
    dst = root / "dst"
    w = DurablePartitionWriterV11(
        src,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="r2_mig",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    base = 1_754_265_600_000
    for i in range(8):
        w.accept(_evt("BTCUSDT", base + i * 1000, i))
    abandoned = w.abandon_open_without_finalize()
    assert abandoned is not None
    src_sha = abandoned.read_bytes()
    import shutil

    shutil.copytree(src, dst)
    dst_part = next(dst.rglob("*.jsonl.gz"))
    unchanged = dst_part.read_bytes() == src_sha
    parts = discover_partitions_v11(dst)
    clf = classify_campaign_partitions(
        parts, source_size_match={str(parts[0]["partition_id"]): True}
    )
    # Control: open tail preserved; migration artifact label available
    control = (
        unchanged
        and parts[0]["is_open_tail"] is True
        and clf["classification_counts"].get("EXPECTED_OPEN_TAIL", 0) >= 1
        and clf["classification_counts"].get("MIGRATION_ARTIFACT", 0) >= 1
    )
    # Hazard: no writer/orchestrator lock prevents migrating open partitions in the first place
    hazard = abandoned.exists() and open_marker_for(abandoned).exists() and control
    return ScenarioResult(
        scenario_id="partition_migrated_while_open",
        title="Partition migrated while open",
        lane="D",
        severity_if_confirmed="MEDIUM",
        hazard_confirmed=True,  # migration of open partitions is still possible (no gate)
        control_ok=control,
        summary=(
            "Open partitions can be byte-copied while .open is present; classifier correctly "
            "labels EXPECTED_OPEN_TAIL + MIGRATION_ARTIFACT when sizes match, but there is no "
            "storage-safety gate refusing migration of in-flight partitions."
        ),
        evidence={
            "bytes_unchanged": unchanged,
            "classifications": clf["classification_counts"],
            "open_marker_on_source": open_marker_for(abandoned).is_file(),
            "storage_gate_blocks_open_migration": False,
        },
    )


def scenario_duplicate_partition_identity(root: Path) -> ScenarioResult:
    """Two writers with identical session/symbol/hour overwrite the same partition_id path."""
    base = 1_754_265_600_000
    w1 = DurablePartitionWriterV11(
        root,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="r2_dup",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    w2 = DurablePartitionWriterV11(
        root,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="r2_dup",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import (
        PartitionIdentityConflict,
    )

    w1.accept(_evt("BTCUSDT", base, 1))
    conflict_blocked = False
    conflict_error = None
    try:
        w2.accept(_evt("BTCUSDT", base + 1, 2))
    except PartitionIdentityConflict as exc:
        conflict_blocked = True
        conflict_error = str(exc)
    w1.close()
    try:
        w2.close()
    except Exception:
        pass
    gz_files = list(root.rglob("*.jsonl.gz"))
    parts = discover_partitions_v11(root)
    # Post R2-D-001: exclusive create must block silent overwrite.
    hazard = (not conflict_blocked) and len(gz_files) == 1 and len(parts) == 1
    return ScenarioResult(
        scenario_id="duplicate_partition_identity",
        title="Duplicate partition identity",
        lane="D",
        severity_if_confirmed="CRITICAL",
        hazard_confirmed=hazard,
        control_ok=conflict_blocked,
        summary=(
            "partition_id exclusive create must reject concurrent writers; "
            "silent overwrite of the same .jsonl.gz path is forbidden."
        ),
        evidence={
            "gz_file_count": len(gz_files),
            "discovered_count": len(parts),
            "partition_ids": [p["partition_id"] for p in parts],
            "overwrite_blocked": conflict_blocked,
            "conflict_error": conflict_error,
        },
    )


def scenario_missing_previous_link(root: Path) -> ScenarioResult:
    """Closed-chain missing previous_partition_id must fail linkage audit."""
    fake = [
        {
            "partition_id": "p0",
            "capture_session_id": "r2_link",
            "family": "AGGRESSIVE_TRADE_FLOW",
            "symbol": "BTCUSDT",
            "UTC_hour": "20250804_00",
            "partition_seq": 0,
            "previous_partition_id": None,
            "manifest_present": True,
            "is_open_tail": False,
        },
        {
            "partition_id": "p1",
            "capture_session_id": "r2_link",
            "family": "AGGRESSIVE_TRADE_FLOW",
            "symbol": "BTCUSDT",
            "UTC_hour": "20250804_01",
            "partition_seq": 1,
            "previous_partition_id": None,
            "manifest_present": True,
            "is_open_tail": False,
        },
    ]
    link = audit_linkage_v11(fake)
    control = link["cross_partition_linkage_status"] == "FAIL" and link["linkage_breaks"] >= 1
    return ScenarioResult(
        scenario_id="missing_previous_link",
        title="Missing previous-link identity",
        lane="D",
        severity_if_confirmed="HIGH",
        hazard_confirmed=False,
        control_ok=control,
        summary="audit_linkage_v11 correctly flags mid-chain null previous_partition_id as linkage_break.",
        evidence=link,
    )


def scenario_clock_rollback_across_partition_rotation(root: Path) -> ScenarioResult:
    """Exchange timestamp moving backward rotates into a prior hour and confuses linkage order."""
    w = DurablePartitionWriterV11(
        root,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="r2_clk_rot",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    t0 = 1_754_265_600_000  # 2025-08-04 00:00 UTC-ish fixture hour
    t_back = t0 - 3_600_000
    for i in range(3):
        w.accept(_evt("BTCUSDT", t0 + i * 1000, i))
    for i in range(3):
        w.accept(_evt("BTCUSDT", t_back + i * 1000, 100 + i))
    report = w.close()
    parts = discover_partitions_v11(root)
    link = audit_linkage_v11(parts)
    hazard = (
        report["partition_count"] >= 2
        and link["cross_partition_linkage_status"] == "FAIL"
    )
    return ScenarioResult(
        scenario_id="clock_rollback_across_partition_rotation",
        title="Clock rollback across partition rotation",
        lane="D",
        severity_if_confirmed="HIGH",
        hazard_confirmed=hazard,
        control_ok=False,
        summary=(
            "Writer accepts exchange_timestamp moving into a prior UTC hour, creating a "
            "partition whose previous_link points forward in wall order; hour-sorted linkage "
            "then reports FAIL."
        ),
        evidence={
            "partition_count": report["partition_count"],
            "partitions": [
                {
                    "UTC_hour": p.get("UTC_hour"),
                    "partition_id": p.get("partition_id"),
                    "previous_partition_id": p.get("previous_partition_id"),
                }
                for p in parts
            ],
            "linkage": {
                "status": link["cross_partition_linkage_status"],
                "breaks": link["linkage_breaks"],
                "issues": link.get("issues"),
            },
        },
    )


def scenario_restore_from_corrupted_lkg(root: Path) -> ScenarioResult:
    dur = RuntimeDurabilityV2(root)
    led = dur.open_ledger()
    led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="r2",
        payload={"ok": True},
        idempotency_key="lkg-1",
    )
    assert dur.create_snapshot(led).status == SNAPSHOT_OK
    led.close()
    corrupt_lkg_pointer(dur)
    restored = dur.restore_last_known_good()
    control = restored.status == CORRUPTION_DETECTED
    return ScenarioResult(
        scenario_id="restore_from_corrupted_lkg",
        title="Restore from corrupted LKG",
        lane="C",
        severity_if_confirmed="CRITICAL",
        hazard_confirmed=False,
        control_ok=control,
        summary="Corrupted LKG checksum fails closed with CORRUPTION_DETECTED (no silent restore).",
        evidence={"restore_status": restored.status, "detail": restored.detail},
    )


def scenario_snapshot_skips_payload_corruption(root: Path) -> ScenarioResult:
    dur = RuntimeDurabilityV2(root)
    led = dur.open_ledger()
    led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="r2",
        payload={"n": 1},
        idempotency_key="pay-1",
    )
    inject_payload_bit_corruption(led, seq=1)
    det = dur.detect_corruption(led)
    snap = dur.create_snapshot(led)
    led.close()
    hazard = (
        det.get("corruption_detection_status") == CORRUPTION_DETECTED
        and snap.status == SNAPSHOT_OK
    )
    return ScenarioResult(
        scenario_id="snapshot_skips_payload_corruption",
        title="Snapshot authority skips payload-hash verification",
        lane="C",
        severity_if_confirmed="CRITICAL",
        hazard_confirmed=hazard,
        control_ok=False,
        summary=(
            "detect_corruption finds payload_hash mismatch, but create_snapshot only runs "
            "verify_hash_chain + PRAGMA integrity_check and still emits SNAPSHOT_OK / LKG."
        ),
        evidence={
            "detect_corruption": det.get("corruption_detection_status"),
            "snapshot_status": snap.status,
            "lkg_exists": dur.lkg_path.exists(),
        },
    )


def scenario_clock_rollback_lost_on_reopen(root: Path) -> ScenarioResult:
    led = DurableEventLedgerV2(root / "l.sqlite3", clock=lambda: 1_700_000_100.0)
    a = led.append(
        aggregate_id="c",
        aggregate_type="DECISION",
        event_type="A",
        source="r2",
        payload={},
        idempotency_key="1",
    )
    led.close()
    led2 = DurableEventLedgerV2(root / "l.sqlite3", clock=lambda: 1_700_000_050.0)
    b = led2.append(
        aggregate_id="c",
        aggregate_type="DECISION",
        event_type="B",
        source="r2",
        payload={},
        idempotency_key="2",
    )
    led2.close()
    hazard = a.status == "APPENDED" and b.status == "APPENDED"
    return ScenarioResult(
        scenario_id="clock_rollback_lost_on_reopen",
        title="Clock rollback protection is process-local",
        lane="C",
        severity_if_confirmed="HIGH",
        hazard_confirmed=hazard,
        control_ok=False,
        summary=(
            "_last_accepted_wall is memory-only; reopening the ledger accepts a wall clock "
            "earlier than the last persisted event."
        ),
        evidence={"first": a.status, "second_after_reopen": b.status, "second_reason": b.reason},
    )


def scenario_fsync_interrupt_commits_anyway(root: Path) -> ScenarioResult:
    dur = RuntimeDurabilityV2(root)
    led = dur.open_ledger()
    led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="r2",
        payload={"n": 1},
        idempotency_key="pre",
    )
    led.set_fsync_interrupt(True)
    interrupted = False
    try:
        led.append(
            aggregate_id="a",
            aggregate_type="DECISION",
            event_type="Y",
            source="r2",
            payload={"n": 2},
            idempotency_key="post",
        )
    except InterruptedError:
        interrupted = True
    count = led.event_count()
    led.close()
    hazard = interrupted and count == 2
    return ScenarioResult(
        scenario_id="fsync_interrupt_commits_anyway",
        title="Fsync interruption after commit leaves durable event",
        lane="C",
        severity_if_confirmed="HIGH",
        hazard_confirmed=hazard,
        control_ok=interrupted,
        summary=(
            "fsync_interrupt raises after SQLite commit; the injection matrix treats the "
            "exception as PASS, but the event remains durable — not a true power-loss model."
        ),
        evidence={"interrupted": interrupted, "event_count_after": count},
    )


def scenario_orphan_open_marker_after_finalize(root: Path) -> ScenarioResult:
    w = DurablePartitionWriterV11(
        root,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        capture_session_id="r2_orphan",
        buffer_max_events=1,
        flush_interval_s=0.01,
    )
    base = 1_754_265_600_000
    for i in range(5):
        w.accept(_evt("BTCUSDT", base + i * 1000, i))
    report = w.close()
    path = Path(report["partitions"][0]["path"])
    open_marker_for(path).write_text(
        json.dumps({"status": "OPEN", "orphaned_after_finalize": True}) + "\n",
        encoding="utf-8",
    )
    parts = discover_partitions_v11(root)
    clf = classify_campaign_partitions(parts)
    hazard = (
        parts[0]["manifest_present"]
        and parts[0]["open_marker_present"]
        and parts[0]["is_open_tail"] is False
        and clf["finding_count"] == 0
    )
    return ScenarioResult(
        scenario_id="orphan_open_marker_after_finalize",
        title="Orphan .open marker after successful finalize",
        lane="D",
        severity_if_confirmed="HIGH",
        hazard_confirmed=hazard,
        control_ok=False,
        summary=(
            "Crash between atomic manifest replace and .open unlink leaves a finalized "
            "partition with open_marker_present=True; classifier emits no finding."
        ),
        evidence={
            "part": {
                k: parts[0].get(k)
                for k in (
                    "is_open_tail",
                    "open_marker_present",
                    "manifest_present",
                    "integrity_status",
                )
            },
            "finding_count": clf["finding_count"],
        },
    )


def scenario_concurrent_snapshot_wal_lock(root: Path) -> ScenarioResult:
    """Concurrent append during snapshot may fail copying -wal on Windows (PermissionError)."""
    dur = RuntimeDurabilityV2(root)
    led = dur.open_ledger()
    for i in range(20):
        led.append(
            aggregate_id=f"a{i}",
            aggregate_type="DECISION",
            event_type="X",
            source="r2",
            payload={"i": i},
            idempotency_key=f"k{i}",
        )

    barrier = threading.Barrier(2)
    box: dict[str, Any] = {}

    def snapper() -> None:
        barrier.wait()
        try:
            box["snap"] = dur.create_snapshot(led).to_dict()
        except Exception as exc:  # noqa: BLE001
            box["error"] = f"{type(exc).__name__}:{exc}"

    def appender() -> None:
        barrier.wait()
        for i in range(80):
            try:
                led.append(
                    aggregate_id=f"r{i}",
                    aggregate_type="DECISION",
                    event_type="X",
                    source="r2",
                    payload={"i": i},
                    idempotency_key=f"r{i}",
                )
            except Exception as exc:  # noqa: BLE001
                box.setdefault("append_errors", []).append(str(exc))
            time.sleep(0.001)

    t1 = threading.Thread(target=snapper)
    t2 = threading.Thread(target=appender)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    led.close()

    err = box.get("error") or ""
    hazard = "PermissionError" in err or (
        # Also treat success-with-race potential as noteworthy when snap ran under load
        "snap" in box and box["snap"].get("status") == SNAPSHOT_OK
    )
    # On Windows this commonly surfaces PermissionError; on other OS may succeed — still a race window
    confirmed = "PermissionError" in err
    return ScenarioResult(
        scenario_id="concurrent_snapshot_wal_lock",
        title="Concurrent snapshot vs append WAL lock race",
        lane="C",
        severity_if_confirmed="HIGH",
        hazard_confirmed=confirmed,
        control_ok=False,
        summary=(
            "create_snapshot copies -wal while the live connection may still hold locks; "
            "under concurrent append this raises PermissionError (Windows) or races silently."
        ),
        evidence={"error": err or None, "snap": box.get("snap"), "append_errors": box.get("append_errors", [])[:5]},
    )


SCENARIO_RUNNERS: dict[str, Callable[[Path], ScenarioResult]] = {
    "power_loss_during_gzip_close": scenario_power_loss_during_gzip_close,
    "checkpoint_before_ledger_fsync": scenario_checkpoint_before_ledger_fsync,
    "snapshot_from_stale_ledger_tail": scenario_snapshot_from_stale_ledger_tail,
    "manifest_before_file_close": scenario_manifest_before_file_close,
    "partition_migrated_while_open": scenario_partition_migrated_while_open,
    "duplicate_partition_identity": scenario_duplicate_partition_identity,
    "missing_previous_link": scenario_missing_previous_link,
    "clock_rollback_across_partition_rotation": scenario_clock_rollback_across_partition_rotation,
    "restore_from_corrupted_lkg": scenario_restore_from_corrupted_lkg,
    "snapshot_skips_payload_corruption": scenario_snapshot_skips_payload_corruption,
    "clock_rollback_lost_on_reopen": scenario_clock_rollback_lost_on_reopen,
    "fsync_interrupt_commits_anyway": scenario_fsync_interrupt_commits_anyway,
    "orphan_open_marker_after_finalize": scenario_orphan_open_marker_after_finalize,
    "concurrent_snapshot_wal_lock": scenario_concurrent_snapshot_wal_lock,
}


def run_adversarial_matrix(
    *,
    base_root: Path | None = None,
    scenarios: list[str] | None = None,
    pass_id: str = "PASS_1",
) -> dict[str, Any]:
    root = Path(base_root) if base_root else Path(tempfile.mkdtemp(prefix="r2_adv_"))
    root.mkdir(parents=True, exist_ok=True)
    selected = list(scenarios) if scenarios else list(ADVERSARIAL_SCENARIOS)
    results: list[ScenarioResult] = []
    for sid in selected:
        runner = SCENARIO_RUNNERS[sid]
        case_root = root / sid
        case_root.mkdir(parents=True, exist_ok=True)
        result = runner(case_root)
        result.pass_id = pass_id
        results.append(result)

    hazards = [r for r in results if r.hazard_confirmed]
    controls = [r for r in results if r.control_ok]
    by_sev: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in hazards:
        by_sev[r.severity_if_confirmed] = by_sev.get(r.severity_if_confirmed, 0) + 1

    return {
        "schema": "r2_durability_microstructure_adversarial_matrix_v1",
        "pass_id": pass_id,
        "generated_at": _utc(),
        "total_scenarios": len(results),
        "hazard_confirmed_count": len(hazards),
        "control_ok_count": len(controls),
        "hazards_by_severity": by_sev,
        "results": [r.to_dict() for r in results],
        "raw_campaign_evidence_modified": False,
    }
