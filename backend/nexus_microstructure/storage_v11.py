"""Streaming partitioned storage for Microstructure V1.1 (no full in-memory records)."""
from __future__ import annotations

import gzip
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_hour_key(exchange_ts_ms: int) -> str:
    dt = datetime.fromtimestamp(exchange_ts_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y%m%d_%H")


class RollingSha256:
    def __init__(self) -> None:
        self._h = hashlib.sha256()
        self.bytes = 0

    def update(self, chunk: bytes) -> None:
        self._h.update(chunk)
        self.bytes += len(chunk)

    def hexdigest(self) -> str:
        return self._h.hexdigest()


class StreamingPartitionWriter:
    """Per symbol/family hourly compressed partitions with rolling checksum."""

    def __init__(
        self,
        root: Path,
        *,
        exchange: str,
        family: str,
        symbol: str,
        capture_session_id: str,
        max_partition_bytes: int = 32 * 1024 * 1024,
        buffer_max_events: int = 200,
        buffer_max_bytes: int = 256 * 1024,
        flush_interval_s: float = 2.0,
    ) -> None:
        self.root = root
        self.exchange = exchange
        self.family = family
        self.symbol = symbol
        self.capture_session_id = capture_session_id
        self.max_partition_bytes = max_partition_bytes
        self.buffer_max_events = buffer_max_events
        self.buffer_max_bytes = buffer_max_bytes
        self.flush_interval_s = flush_interval_s
        self.dir = root / exchange / family / symbol
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
        self.full_records_retained_in_memory = False
        self.storage_tree_scanned_per_event = False

    def _open_partition(self, hour: str) -> None:
        self._close_partition(rotate=True)
        pid = f"{self.capture_session_id}_{self.family}_{self.symbol}_{hour}_{self.partition_count}"
        self._path = self.dir / f"{pid}.jsonl.gz"
        # Unique partition path per open — use wb so gzip EOS is always owned by this handle.
        # Append mode ("ab") produced truncated members under process/cloud interruption.
        self._fh = gzip.open(self._path, "wb")
        self._rolling = RollingSha256()
        self._hour = hour
        self._record_count = 0
        self._first_ex = self._last_ex = None
        self._first_rx = self._last_rx = None
        self._partition_bytes = 0
        self.partition_count += 1

    def _manifest(self, *, checksum_match: bool | None = None) -> dict[str, Any]:
        assert self._path is not None and self._rolling is not None
        compressed = self._path.stat().st_size if self._path.exists() else 0
        return {
            "partition_id": self._path.stem,
            "exchange": self.exchange,
            "family": self.family,
            "symbol": self.symbol,
            "UTC_hour": self._hour,
            "schema_version": "microstructure_data_foundation_v1_1",
            "record_count": self._record_count,
            "first_exchange_timestamp": self._first_ex,
            "last_exchange_timestamp": self._last_ex,
            "first_receive_timestamp": self._first_rx,
            "last_receive_timestamp": self._last_rx,
            "uncompressed_bytes": self._rolling.bytes,
            "compressed_bytes": compressed,
            "compression_ratio": (compressed / self._rolling.bytes) if self._rolling.bytes else None,
            "rolling_checksum": self._rolling.hexdigest(),
            "previous_partition_id": self._prev_partition_id,
            "capture_session_id": self.capture_session_id,
            "path": str(self._path),
            "checksum_match": checksum_match,
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

    def _replay_checksum(self, path: Path) -> str | None:
        h = hashlib.sha256()
        try:
            with gzip.open(path, "rb") as fh:
                while True:
                    chunk = fh.read(1024 * 256)
                    if not chunk:
                        break
                    h.update(chunk)
        except EOFError:
            return None
        return h.hexdigest()

    def _close_partition(self, *, rotate: bool) -> None:
        if self._fh is None or self._path is None or self._rolling is None:
            return
        self.flush()
        self._fh.close()
        replayed = self._replay_checksum(self._path)
        match = bool(replayed) and replayed == self._rolling.hexdigest()
        man = self._manifest(checksum_match=match)
        man["replayed_checksum"] = replayed
        if replayed is None:
            man["integrity_status"] = "TRUNCATED_OR_INCOMPLETE"
        man_path = self._path.with_suffix(".manifest.json")
        man_path.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
        self.partitions.append(man)
        self._prev_partition_id = man["partition_id"]
        self._fh = None
        self._path = None
        self._rolling = None
        self._hour = None

    def close(self) -> dict[str, Any]:
        self._close_partition(rotate=False)
        self.closed = True
        return {
            "family": self.family,
            "symbol": self.symbol,
            "partition_count": len(self.partitions),
            "partitions": self.partitions,
            "session_bytes_written": self.session_bytes_written,
            "writers_closed": True,
            "buffers_flushed": True,
            "manifest_complete": all(p.get("checksum_match") is not None for p in self.partitions),
            "checksum_replay_verified": all(bool(p.get("checksum_match")) for p in self.partitions)
            if self.partitions
            else True,
            "full_records_retained_in_memory": False,
            "storage_tree_scanned_per_event": False,
        }


def utc_now_ms() -> int:
    return int(time.time() * 1000)
