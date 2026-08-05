"""Runtime Durability V2 engine — snapshots, LKG, checkpoint, corruption detection."""
from __future__ import annotations

import gc
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_runtime.durability_v2.constants import (
    BLOCKED_AMBIGUOUS_STATE,
    CORRUPTION_DETECTED,
    PRESERVED_FACTS,
    RECOVERED_EXACT,
    RECOVERED_LAST_KNOWN_GOOD,
    RECOVERY_FAILED,
    SNAPSHOT_OK,
)
from backend.nexus_runtime.durability_v2.ledger import DurableEventLedgerV2
from backend.nexus_runtime.durability_v2.metrics import LatencyHistogram


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


@dataclass
class SnapshotResult:
    status: str
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, **self.detail}


class RuntimeDurabilityV2:
    """Snapshots + last-known-good with fail-closed restore semantics."""

    def __init__(
        self,
        root: Path,
        *,
        backup_root: Path | None = None,
        soft_disk_limit_bytes: int | None = None,
        hard_disk_limit_bytes: int | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.backup_root = Path(backup_root) if backup_root else self.root / "snapshots"
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "event_ledger_v2.sqlite3"
        self.lkg_path = self.root / "last_known_good.json"
        self.meta_path = self.root / "durability_meta_v2.json"
        self.checkpoint_path = self.root / "checkpoint_v2.json"
        self._generation = 0
        self._soft = soft_disk_limit_bytes
        self._hard = hard_disk_limit_bytes
        self.snapshot_latency = LatencyHistogram("snapshot")
        self.restore_latency = LatencyHistogram("restore")
        if self.meta_path.exists():
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            self._generation = int(meta.get("generation") or 0)

    def open_ledger(self, **kwargs: Any) -> DurableEventLedgerV2:
        kw = dict(kwargs)
        if "soft_disk_limit_bytes" not in kw and self._soft is not None:
            kw["soft_disk_limit_bytes"] = self._soft
        if "hard_disk_limit_bytes" not in kw and self._hard is not None:
            kw["hard_disk_limit_bytes"] = self._hard
        return DurableEventLedgerV2(self.ledger_path, **kw)

    def _write_meta(self) -> None:
        self.meta_path.write_text(
            json.dumps(
                {"generation": self._generation, "updated_at": _utc(), **PRESERVED_FACTS},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def create_snapshot(
        self,
        ledger: DurableEventLedgerV2,
        *,
        verify_chain: bool = True,
        kill_during_checkpoint: bool = False,
    ) -> SnapshotResult:
        t0 = time.perf_counter()
        if verify_chain:
            chain = ledger.verify_hash_chain()
            if chain.get("ledger_hash_chain_status") != "PASS":
                return SnapshotResult(status=CORRUPTION_DETECTED, detail={"chain": chain})
            integrity = ledger.integrity_check()
            if integrity != "ok":
                return SnapshotResult(
                    status=CORRUPTION_DETECTED, detail={"integrity": integrity}
                )
        else:
            chain = {"ledger_hash_chain_status": "DEFERRED"}

        if kill_during_checkpoint:
            # Simulate process kill mid-checkpoint: write partial marker, no LKG update.
            partial = self.root / "checkpoint_partial.marker"
            partial.write_text(
                json.dumps({"status": "PARTIAL", "at": _utc()}, indent=2) + "\n",
                encoding="utf-8",
            )
            return SnapshotResult(
                status="CHECKPOINT_INTERRUPTED",
                detail={"reason": "process_kill_during_checkpoint", "partial_marker": str(partial)},
            )

        self._generation += 1
        gen = self._generation
        snap_dir = self.backup_root / f"snapshot_{gen:06d}"
        snap_dir.mkdir(parents=True, exist_ok=True)
        dest = snap_dir / "event_ledger_v2.sqlite3"

        try:
            ledger._conn.execute("PRAGMA wal_checkpoint(FULL)")
        except Exception:
            pass
        ledger._conn.commit()
        shutil.copy2(self.ledger_path, dest)
        for suffix in ("-wal", "-shm"):
            side = Path(str(self.ledger_path) + suffix)
            if side.exists():
                shutil.copy2(side, Path(str(dest) + suffix))

        checksum = file_sha256(dest)
        pointer = {
            "generation": gen,
            "created_at": _utc(),
            "source_ledger_position": ledger.event_count(),
            "max_sequence": ledger.max_sequence(),
            "snapshot_checksum": checksum,
            "snapshot_path": str(dest),
            "ledger_hash_chain_status": chain.get("ledger_hash_chain_status"),
            "schema": "durability_v2",
        }
        (snap_dir / "snapshot_manifest.json").write_text(
            json.dumps(pointer, indent=2) + "\n", encoding="utf-8"
        )
        self.lkg_path.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
        self.checkpoint_path.write_text(
            json.dumps(
                {
                    "checkpoint_id": f"ckpt-{gen:06d}",
                    "lkg_generation": gen,
                    "created_at": _utc(),
                    "ledger_position": pointer["source_ledger_position"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_meta()
        elapsed = time.perf_counter() - t0
        self.snapshot_latency.observe(elapsed)
        return SnapshotResult(status=SNAPSHOT_OK, detail={**pointer, "latency_s": elapsed})

    def detect_corruption(
        self,
        ledger: DurableEventLedgerV2,
        *,
        deep: bool = True,
    ) -> dict[str, Any]:
        integrity = ledger.integrity_check()
        chain = ledger.verify_hash_chain()
        status = "PASS"
        if integrity != "ok" or chain.get("ledger_hash_chain_status") != "PASS":
            status = CORRUPTION_DETECTED
        # Verify payload_hash matches payload_json (detects silent bit flips).
        count = ledger.event_count()
        payload_mismatch = False
        if count > 0 and status == "PASS":
            if deep and count <= 20_000:
                rows = ledger._conn.execute(
                    "SELECT sequence_number, payload_json, payload_hash FROM events "
                    "ORDER BY sequence_number ASC"
                ).fetchall()
            else:
                # Sampled deep-check: always cover head+tail (+ mid when deep).
                head = ledger._conn.execute(
                    "SELECT sequence_number, payload_json, payload_hash FROM events "
                    "ORDER BY sequence_number ASC LIMIT 200"
                ).fetchall()
                tail = ledger._conn.execute(
                    "SELECT sequence_number, payload_json, payload_hash FROM events "
                    "ORDER BY sequence_number DESC LIMIT 200"
                ).fetchall()
                rows = list(head) + list(tail)
                if deep and count > 400:
                    mid = max(1, count // 2)
                    mid_rows = ledger._conn.execute(
                        "SELECT sequence_number, payload_json, payload_hash FROM events "
                        "WHERE sequence_number BETWEEN ? AND ? ORDER BY sequence_number ASC",
                        (mid - 50, mid + 50),
                    ).fetchall()
                    rows = list(rows) + list(mid_rows)
            for r in rows:
                expected = hashlib.sha256(r["payload_json"].encode("utf-8")).hexdigest()
                if expected != r["payload_hash"]:
                    payload_mismatch = True
                    break
            if payload_mismatch:
                status = CORRUPTION_DETECTED
                chain = {**chain, "payload_hash_mismatch": True}
        return {
            "corruption_detection_status": status,
            "integrity_check": integrity,
            **chain,
        }

    def list_snapshots(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.backup_root.exists():
            return out
        for d in sorted(self.backup_root.glob("snapshot_*")):
            man = d / "snapshot_manifest.json"
            if man.exists():
                out.append(json.loads(man.read_text(encoding="utf-8")))
        return out

    def latest_snapshot_manifest(self) -> dict[str, Any] | None:
        snaps = self.list_snapshots()
        return snaps[-1] if snaps else None

    def restore_last_known_good(self, *, allow_ambiguous: bool = False) -> SnapshotResult:
        """Restore from LKG. Never silently guesses when state is ambiguous."""
        t0 = time.perf_counter()
        if not self.lkg_path.exists():
            return SnapshotResult(
                status=RECOVERY_FAILED, detail={"reason": "missing_lkg_pointer"}
            )
        try:
            pointer = json.loads(self.lkg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return SnapshotResult(
                status=CORRUPTION_DETECTED,
                detail={"reason": "lkg_unreadable", "error": str(exc)},
            )

        snap = Path(pointer.get("snapshot_path") or "")
        if not snap.exists():
            # Latest missing — ambiguous; do not invent a recovery.
            return SnapshotResult(
                status=BLOCKED_AMBIGUOUS_STATE,
                detail={"reason": "latest_snapshot_missing", "pointer": pointer},
            )

        actual = file_sha256(snap)
        if actual != pointer.get("snapshot_checksum"):
            return SnapshotResult(
                status=CORRUPTION_DETECTED,
                detail={
                    "reason": "snapshot_checksum_mismatch",
                    "expected": pointer.get("snapshot_checksum"),
                    "actual": actual,
                },
            )

        # Validate LKG generation vs available snapshots when checkpoint says otherwise.
        latest = self.latest_snapshot_manifest()
        if latest and int(latest.get("generation") or 0) != int(pointer.get("generation") or -1):
            # Divergence between LKG pointer and latest on-disk snapshot is ambiguous.
            if not allow_ambiguous:
                return SnapshotResult(
                    status=BLOCKED_AMBIGUOUS_STATE,
                    detail={
                        "reason": "lkg_vs_latest_generation_mismatch",
                        "lkg_generation": pointer.get("generation"),
                        "latest_generation": latest.get("generation"),
                    },
                )

        tmp = self.root / "restore_tmp_v2.sqlite3"
        shutil.copy2(snap, tmp)
        probe = DurableEventLedgerV2(tmp)
        try:
            # Snapshot bytes already checksum-matched; use sampled payload verify.
            det = self.detect_corruption(probe, deep=False)
            if det.get("corruption_detection_status") != "PASS":
                probe.close()
                tmp.unlink(missing_ok=True)
                return SnapshotResult(status=CORRUPTION_DETECTED, detail=det)
            count = probe.event_count()
            max_seq = probe.max_sequence()
            probe.close()
        except Exception as exc:
            try:
                probe.close()
            except Exception:
                pass
            tmp.unlink(missing_ok=True)
            return SnapshotResult(status=RECOVERY_FAILED, detail={"error": str(exc)})

        live_ok = True
        live_count = None
        if self.ledger_path.exists():
            live = None
            try:
                live = DurableEventLedgerV2(self.ledger_path)
                live_det = self.detect_corruption(live, deep=False)
                live_count = live.event_count()
                if live_det.get("corruption_detection_status") != "PASS":
                    live_ok = False
            except Exception:
                live_ok = False
            finally:
                if live is not None:
                    try:
                        live.close()
                    except Exception:
                        pass

        # If live has MORE valid events than snapshot and is healthy, restoring would
        # discard evidence without proof of loss — block as ambiguous.
        if (
            live_ok
            and live_count is not None
            and live_count > count
            and not allow_ambiguous
        ):
            tmp.unlink(missing_ok=True)
            return SnapshotResult(
                status=BLOCKED_AMBIGUOUS_STATE,
                detail={
                    "reason": "live_ahead_of_lkg_would_discard_evidence",
                    "live_count": live_count,
                    "lkg_count": count,
                    "evidence_loss_claimed_without_proof": False,
                },
            )

        # Replace live ledger atomically-ish (Windows-safe): swap aside then copy.
        gc.collect()
        aside = self.root / "ledger_aside_v2.sqlite3"
        for attempt in range(8):
            try:
                if self.ledger_path.exists():
                    if aside.exists():
                        aside.unlink()
                    try:
                        os.replace(self.ledger_path, aside)
                    except OSError:
                        shutil.copy2(self.ledger_path, aside)
                        self.ledger_path.unlink()
                shutil.copy2(tmp, self.ledger_path)
                break
            except PermissionError:
                time.sleep(0.05 * (attempt + 1))
                gc.collect()
        else:
            tmp.unlink(missing_ok=True)
            return SnapshotResult(
                status=RECOVERY_FAILED,
                detail={"reason": "windows_file_lock_replace_failed"},
            )
        tmp.unlink(missing_ok=True)
        aside.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            side = Path(str(self.ledger_path) + suffix)
            for _ in range(5):
                try:
                    side.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.05)
                    gc.collect()

        elapsed = time.perf_counter() - t0
        self.restore_latency.observe(elapsed)
        detail = {
            "generation": pointer.get("generation"),
            "event_count": count,
            "max_sequence": max_seq,
            "live_ok_before": live_ok,
            "latency_s": elapsed,
        }
        if live_ok and count == pointer.get("source_ledger_position"):
            return SnapshotResult(status=RECOVERED_EXACT, detail=detail)
        return SnapshotResult(status=RECOVERED_LAST_KNOWN_GOOD, detail=detail)

    def fail_closed_ambiguous(self, *, reason: str) -> dict[str, Any]:
        return {
            "status": BLOCKED_AMBIGUOUS_STATE,
            "reason": reason,
            "exchange_write_attempt_count": 0,
            "demo_order_count": 0,
            "policy_mutation": False,
            "silent_recovery_guess": False,
            **PRESERVED_FACTS,
        }

    def disk_usage_bytes(self) -> int:
        total = 0
        for p in self.root.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return total
