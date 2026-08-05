"""Cutover V2 durable partition writer — exclusive IDs, atomic seal, clock/resume."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.collector_cutover_v2.clock_guard import PersistentClockGuard
from backend.nexus_microstructure.collector_cutover_v2.constants import (
    SCHEMA,
    SEAL_STATE_SUFFIX,
)
from backend.nexus_microstructure.collector_cutover_v2.resume_linkage import ResumeSafeLinkage
from backend.nexus_microstructure.integrity_recovery_v11.checksum import replay_gzip_sha256
from backend.nexus_microstructure.integrity_recovery_v11.path_identity import partition_id_from_gz
from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import (
    PartitionIdentityConflict,
    RollingSha256,
    _exclusive_gzip_create,
    manifest_path_for,
    open_marker_for,
    utc_now_ms,
)


def seal_state_path_for(gz_path: Path) -> Path:
    return Path(str(gz_path) + SEAL_STATE_SUFFIX)


class DurablePartitionWriterV2:
    """Collector Cutover V2 writer.

    Hardening vs V11:
    - Persistent clock guard (survives reopen)
    - Refuse backward hour rotation without resume boundary (R2-D-003)
    - Resume-safe previous_partition_id linkage
    - Seal-state protocol: FINALIZING → atomic manifest → SEALED → unlink .open
    - Exclusive O_EXCL create retained (R2-D-001)
    """

    def __init__(
        self,
        root: Path,
        *,
        exchange: str,
        family: str,
        symbol: str,
        capture_session_id: str,
        max_partition_bytes: int = 32 * 1024 * 1024,
        buffer_max_events: int = 50,
        buffer_max_bytes: int = 64 * 1024,
        flush_interval_s: float = 0.5,
        session_meta_dir: Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.exchange = exchange
        self.family = family
        self.symbol = symbol
        self.capture_session_id = capture_session_id
        self.max_partition_bytes = max_partition_bytes
        self.buffer_max_events = buffer_max_events
        self.buffer_max_bytes = buffer_max_bytes
        self.flush_interval_s = flush_interval_s
        self.dir = self.root / exchange / family / symbol
        self.dir.mkdir(parents=True, exist_ok=True)
        meta = Path(session_meta_dir) if session_meta_dir else (self.root / "_session_meta" / capture_session_id)
        meta.mkdir(parents=True, exist_ok=True)
        self.clock = PersistentClockGuard(meta, capture_session_id=capture_session_id)
        self.linkage = ResumeSafeLinkage(meta, capture_session_id=capture_session_id)
        self.partitions: list[dict[str, Any]] = []
        self._hour: str | None = None
        self._path: Path | None = None
        self._fh = None
        self._rolling: RollingSha256 | None = None
        self._buf: list[bytes] = []
        self._buf_bytes = 0
        self._last_flush = time.time()
        self._record_count = 0
        self._first_ex = None
        self._last_ex = None
        self._first_rx = None
        self._last_rx = None
        self._partition_bytes = 0
        self.partition_count = 0
        self.closed = False
        self.session_bytes_written = 0
        self.session_manifest_bytes = 0
        self.session_compressed_bytes = 0

    def arm_resume_boundary(self) -> None:
        self.clock.arm_resume_boundary()
        self.linkage.resume_boundary_armed = True
        self.linkage._persist()

    def _open_partition(self, hour: str) -> None:
        self._close_partition(rotate=True)
        seq = self.partition_count
        pid = f"{self.capture_session_id}_{self.family}_{self.symbol}_{hour}_{seq}"
        self._path = self.dir / f"{pid}.jsonl.gz"
        marker = open_marker_for(self._path)
        seal = seal_state_path_for(self._path)
        if self._path.exists() or marker.exists() or manifest_path_for(self._path).exists() or seal.exists():
            raise PartitionIdentityConflict(pid, self._path)
        self._fh = _exclusive_gzip_create(self._path)
        marker.write_text(
            json.dumps(
                {
                    "status": "OPEN",
                    "partition_id": pid,
                    "opened_at_unix": time.time(),
                    "capture_session_id": self.capture_session_id,
                    "schema": f"{SCHEMA}_open_marker",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self._rolling = RollingSha256()
        self._hour = hour
        self._record_count = 0
        self._first_ex = self._last_ex = None
        self._first_rx = self._last_rx = None
        self._partition_bytes = 0
        self.partition_count += 1

    def _manifest_body(self, *, checksum_match: bool | None, replayed: str | None) -> dict[str, Any]:
        assert self._path is not None and self._rolling is not None
        compressed = self._path.stat().st_size if self._path.exists() else 0
        pid = partition_id_from_gz(self._path)
        if pid.endswith(".jsonl"):
            pid = pid[: -len(".jsonl")]
        return {
            "partition_id": pid,
            "exchange": self.exchange,
            "family": self.family,
            "symbol": self.symbol,
            "UTC_hour": self._hour,
            "schema_version": SCHEMA,
            "record_count": self._record_count,
            "first_exchange_timestamp": self._first_ex,
            "last_exchange_timestamp": self._last_ex,
            "first_receive_timestamp": self._first_rx,
            "last_receive_timestamp": self._last_rx,
            "uncompressed_bytes": self._rolling.bytes,
            "compressed_bytes": compressed,
            "compression_ratio": (compressed / self._rolling.bytes) if self._rolling.bytes else None,
            "rolling_checksum": self._rolling.hexdigest(),
            "replayed_checksum": replayed,
            "previous_partition_id": self.linkage.previous_for_next_partition(),
            "capture_session_id": self.capture_session_id,
            "path": str(self._path),
            "checksum_match": checksum_match,
            "open_tail": False,
            "finalized": True,
            "seal_protocol": "collector_cutover_v2",
        }

    def flush(self) -> None:
        if not self._buf or self._fh is None or self._rolling is None:
            return
        for chunk in self._buf:
            self._fh.write(chunk)
            self._rolling.update(chunk)
            self._partition_bytes += len(chunk)
            self.session_bytes_written += len(chunk)
        self._fh.flush()
        try:
            os.fsync(self._fh.fileno())
        except (OSError, AttributeError, ValueError):
            pass
        self._buf.clear()
        self._buf_bytes = 0
        self._last_flush = time.time()

    def accept(self, event: dict[str, Any]) -> bool:
        if self.closed:
            return False
        ex = int(event.get("exchange_timestamp") or 0)
        rx = int(event.get("receive_wall_timestamp") or event.get("receive_timestamp") or 0)
        hour = self.clock.accept(ex or utc_now_ms())
        if self._hour != hour or self._fh is None:
            self._open_partition(hour)
        if self._partition_bytes >= self.max_partition_bytes:
            self._open_partition(hour)
        line = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        self._buf.append(line)
        self._buf_bytes += len(line)
        self._record_count += 1
        if self._first_ex is None:
            self._first_ex = ex
            self._first_rx = rx
        self._last_ex = ex
        self._last_rx = rx
        if (
            len(self._buf) >= self.buffer_max_events
            or self._buf_bytes >= self.buffer_max_bytes
            or (time.time() - self._last_flush) >= self.flush_interval_s
        ):
            self.flush()
        return True

    def _write_seal_state(self, path: Path, status: str, extra: dict[str, Any] | None = None) -> None:
        seal = seal_state_path_for(path)
        body = {
            "schema": f"{SCHEMA}_seal_state",
            "status": status,
            "partition_id": partition_id_from_gz(path).removesuffix(".jsonl"),
            "updated_at_unix": time.time(),
            **(extra or {}),
        }
        tmp = Path(str(seal) + ".tmp")
        tmp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, seal)

    def _close_partition(self, *, rotate: bool) -> None:
        if self._fh is None or self._path is None or self._rolling is None:
            return
        self.flush()
        path = self._path
        self._fh.close()
        self._fh = None
        # Phase: gzip closed → FINALIZING seal state (authority for interrupted finalize).
        self._write_seal_state(path, "FINALIZING")
        replay = replay_gzip_sha256(path)
        replayed = replay.get("replayed_checksum")
        match = bool(replayed) and replayed == self._rolling.hexdigest()
        man = self._manifest_body(checksum_match=match, replayed=replayed)
        if replay.get("truncated_tail"):
            man["integrity_status"] = "TRUNCATED_OR_INCOMPLETE"
            man["open_tail"] = True
            man["finalized"] = False
        man_path = manifest_path_for(path)
        tmp = man_path.with_suffix(man_path.suffix + ".tmp")
        tmp.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, man_path)
        self.session_manifest_bytes += man_path.stat().st_size
        self.session_compressed_bytes += int(man.get("compressed_bytes") or 0)
        self._write_seal_state(path, "SEALED", {"manifest_path": str(man_path)})
        marker = open_marker_for(path)
        if marker.exists():
            marker.unlink()
        seal = seal_state_path_for(path)
        if seal.exists():
            seal.unlink()
        self.partitions.append(man)
        if man.get("finalized"):
            self.linkage.record_sealed(man["partition_id"])
        else:
            self.linkage.record_open_tail(man["partition_id"])
        self._path = None
        self._rolling = None
        self._hour = None

    def abandon_open_without_finalize(self) -> Path | None:
        """Simulate process kill: retain .open + truncated gzip."""
        if self._fh is None or self._path is None:
            return None
        path = self._path
        pid = partition_id_from_gz(path).removesuffix(".jsonl")
        try:
            self.flush()
            raw = getattr(self._fh, "fileobj", None)
            if raw is not None:
                self._fh.fileobj = None
            try:
                self._fh.close()
            except Exception:  # noqa: BLE001
                pass
            if raw is not None:
                try:
                    raw.flush()
                    os.fsync(raw.fileno())
                except (OSError, ValueError):
                    pass
                try:
                    raw.close()
                except Exception:  # noqa: BLE001
                    pass
            self.linkage.record_open_tail(pid)
            self.clock.arm_resume_boundary()
        finally:
            self._fh = None
            self._path = None
            self._rolling = None
            self._hour = None
            self._buf.clear()
            self._buf_bytes = 0
        return path

    def close(self) -> dict[str, Any]:
        self._close_partition(rotate=False)
        self.closed = True
        return {
            "schema": f"{SCHEMA}_writer_close",
            "family": self.family,
            "symbol": self.symbol,
            "partition_count": len(self.partitions),
            "partitions": self.partitions,
            "session_bytes_written": self.session_bytes_written,
            "session_manifest_bytes": self.session_manifest_bytes,
            "session_compressed_bytes": self.session_compressed_bytes,
            "writers_closed": True,
            "buffers_flushed": True,
            "manifest_complete": all(p.get("finalized") for p in self.partitions),
            "checksum_replay_verified": all(bool(p.get("checksum_match")) for p in self.partitions)
            if self.partitions
            else True,
            "graceful_stop": True,
            "clock_watermark": self.clock.snapshot(),
            "linkage": self.linkage.snapshot(),
            "exclusive_partition_ids": True,
            "atomic_manifest_seal": True,
        }
