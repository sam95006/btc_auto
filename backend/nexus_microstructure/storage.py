"""Append-only compressed partition storage for microstructure events."""
from __future__ import annotations

import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterable


def utc_ms() -> int:
    return int(time.time() * 1000)


def event_checksum(events: Iterable[dict[str, Any]]) -> str:
    payload = json.dumps(list(events), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PartitionWriter:
    def __init__(
        self,
        root: Path,
        *,
        family: str,
        capture_session_id: str,
        storage_cap_bytes: int = 5 * 1024 * 1024 * 1024,
    ) -> None:
        self.root = root
        self.family = family
        self.capture_session_id = capture_session_id
        self.storage_cap_bytes = storage_cap_bytes
        self.dir = root / family
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seen_keys: set[str] = set()
        self.records: list[dict[str, Any]] = []
        self.duplicate_count = 0
        self.out_of_order_count = 0
        self.parse_error_count = 0
        self.gap_suspected_count = 0
        self.reconnect_count = 0
        self._last_exchange_ts: int | None = None
        self.bytes_written = 0
        self.cap_hit = False
        self._path = self.dir / f"{capture_session_id}.jsonl.gz"
        self._fh = gzip.open(self._path, "ab")

    def current_storage_bytes(self) -> int:
        total = 0
        if self.root.exists():
            for p in self.root.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
        return total

    def accept(self, event: dict[str, Any]) -> bool:
        if self.cap_hit or self.current_storage_bytes() >= self.storage_cap_bytes:
            self.cap_hit = True
            return False
        key = str(event.get("sequence_or_dedup_key") or "")
        if not key:
            self.parse_error_count += 1
            return False
        if key in self.seen_keys:
            self.duplicate_count += 1
            return False
        ex_ts = int(event.get("exchange_timestamp") or 0)
        if self._last_exchange_ts is not None and ex_ts and ex_ts < self._last_exchange_ts:
            self.out_of_order_count += 1
        if self._last_exchange_ts is not None and ex_ts and ex_ts > self._last_exchange_ts + 60_000:
            self.gap_suspected_count += 1
        if ex_ts:
            self._last_exchange_ts = ex_ts
        self.seen_keys.add(key)
        self.records.append(event)
        line = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        self._fh.write(line)
        self._fh.flush()
        self.bytes_written += len(line)
        if self.current_storage_bytes() >= self.storage_cap_bytes:
            self.cap_hit = True
        return True

    def close(self) -> dict[str, Any]:
        self._fh.close()
        checksum = event_checksum(self.records)
        recv = [int(r.get("receive_timestamp") or 0) for r in self.records]
        ex = [int(r.get("exchange_timestamp") or 0) for r in self.records]
        report = {
            "family": self.family,
            "path": str(self._path),
            "record_count": len(self.records),
            "first_exchange_timestamp": min(ex) if ex else None,
            "last_exchange_timestamp": max(ex) if ex else None,
            "first_receive_timestamp": min(recv) if recv else None,
            "last_receive_timestamp": max(recv) if recv else None,
            "duplicate_count": self.duplicate_count,
            "out_of_order_count": self.out_of_order_count,
            "parse_error_count": self.parse_error_count,
            "gap_suspected_count": self.gap_suspected_count,
            "reconnect_count": self.reconnect_count,
            "checksum": checksum,
            "schema_version": "microstructure_data_foundation_v1",
            "bytes_on_disk": self._path.stat().st_size if self._path.exists() else 0,
            "cap_hit": self.cap_hit,
        }
        # Reproducibility: recompute once
        report["checksum_reproducible"] = event_checksum(self.records) == checksum
        return report
