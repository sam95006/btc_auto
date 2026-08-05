"""Hardened streaming partition writer (collector-side fixes) — owned V11 module only.

Does not mutate existing campaign partitions. New captures under caller-provided roots.
Fixes vs storage_v11:
- Explicit .open marker for in-flight partitions (graceful-stop / kill forensics)
- Atomic manifest finalize (temp + replace) after gzip close + flush
- Manifest path uses *.manifest.json (replace .jsonl.gz), not *.jsonl.manifest.json ambiguity
- partition_id strips .jsonl.gz cleanly
- previous_partition_id maintained across hour rotation within writer
- close() seals open tail; kill without close leaves .open + truncated gzip detectable
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.integrity_recovery_v11.checksum import replay_gzip_sha256
from backend.nexus_microstructure.integrity_recovery_v11.path_identity import partition_id_from_gz


def _utc_hour_key(exchange_ts_ms: int) -> str:
    dt = datetime.fromtimestamp(exchange_ts_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y%m%d_%H")


def utc_now_ms() -> int:
    return int(time.time() * 1000)


class RollingSha256:
    def __init__(self) -> None:
        self._h = hashlib.sha256()
        self.bytes = 0

    def update(self, chunk: bytes) -> None:
        self._h.update(chunk)
        self.bytes += len(chunk)

    def hexdigest(self) -> str:
        return self._h.hexdigest()


def manifest_path_for(gz_path: Path) -> Path:
    gz_path = Path(gz_path)
    if gz_path.name.endswith(".jsonl.gz"):
        return gz_path.with_name(gz_path.name.replace(".jsonl.gz", ".manifest.json"))
    return gz_path.with_suffix(".manifest.json")


def open_marker_for(gz_path: Path) -> Path:
    return Path(str(gz_path) + ".open")


class DurablePartitionWriterV11:
    """Per symbol/family hourly compressed partitions with durable finalize semantics."""

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
        self._prev_partition_id: str | None = None
        self.partition_count = 0
        self.closed = False
        self.session_bytes_written = 0
        self.session_manifest_bytes = 0
        self.session_compressed_bytes = 0

    def _open_partition(self, hour: str) -> None:
        self._close_partition(rotate=True)
        seq = self.partition_count
        pid = f"{self.capture_session_id}_{self.family}_{self.symbol}_{hour}_{seq}"
        self._path = self.dir / f"{pid}.jsonl.gz"
        self._fh = gzip.open(self._path, "wb")
        open_marker_for(self._path).write_text(
            json.dumps(
                {
                    "status": "OPEN",
                    "partition_id": pid,
                    "opened_at_unix": time.time(),
                    "capture_session_id": self.capture_session_id,
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
        # Prefer clean id without .jsonl suffix for new captures.
        if pid.endswith(".jsonl"):
            pid = pid[: -len(".jsonl")]
        return {
            "partition_id": pid,
            "exchange": self.exchange,
            "family": self.family,
            "symbol": self.symbol,
            "UTC_hour": self._hour,
            "schema_version": "microstructure_integrity_recovery_v11",
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
            "previous_partition_id": self._prev_partition_id,
            "capture_session_id": self.capture_session_id,
            "path": str(self._path),
            "checksum_match": checksum_match,
            "open_tail": False,
            "finalized": True,
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
        hour = _utc_hour_key(ex or utc_now_ms())
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

    def _close_partition(self, *, rotate: bool) -> None:
        if self._fh is None or self._path is None or self._rolling is None:
            return
        self.flush()
        self._fh.close()
        self._fh = None
        replay = replay_gzip_sha256(self._path)
        replayed = replay.get("replayed_checksum")
        match = bool(replayed) and replayed == self._rolling.hexdigest()
        man = self._manifest_body(checksum_match=match, replayed=replayed)
        if replay.get("truncated_tail"):
            man["integrity_status"] = "TRUNCATED_OR_INCOMPLETE"
            man["open_tail"] = True
            man["finalized"] = False
        man_path = manifest_path_for(self._path)
        tmp = man_path.with_suffix(man_path.suffix + ".tmp")
        tmp.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, man_path)
        self.session_manifest_bytes += man_path.stat().st_size
        self.session_compressed_bytes += int(man.get("compressed_bytes") or 0)
        marker = open_marker_for(self._path)
        if marker.exists():
            marker.unlink()
        self.partitions.append(man)
        self._prev_partition_id = man["partition_id"]
        self._path = None
        self._rolling = None
        self._hour = None

    def abandon_open_without_finalize(self) -> Path | None:
        """Simulate process kill: flush bytes, close raw fd, skip gzip footer + manifest."""
        if self._fh is None or self._path is None:
            return None
        path = self._path
        try:
            self.flush()
            raw = getattr(self._fh, "fileobj", None)
            # Prevent GzipFile.close from writing CRC/ISIZE trailer.
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
            # .open marker intentionally retained for forensics.
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
        }
