"""Date-partitioned ingest manifest."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.nexus_incremental_backfill_live_ingest.constants import SCHEMA_MANIFEST
from backend.nexus_incremental_backfill_live_ingest.hashing import day_partition, sha_obj, utc_now_iso


class DatePartitionManifest:
    """Append-only JSONL manifest keyed by UTC day partitions."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "date_partition_manifest.jsonl"
        self.index_path = self.root / "partition_index.json"
        self._index: dict[str, list[str]] = self._load_index()

    def _load_index(self) -> dict[str, list[str]]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        payload = json.dumps(self._index, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.index_path)

    def append(
        self,
        *,
        exchange_timestamp: str,
        content_hash: str,
        symbol: str,
        source_id: str,
        data_class: str,
        status: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        day = day_partition(exchange_timestamp)
        entry = {
            "schema": SCHEMA_MANIFEST,
            "day_utc": day,
            "exchange_timestamp": exchange_timestamp,
            "content_hash": content_hash,
            "symbol": symbol,
            "source_id": source_id,
            "data_class": data_class,
            "status": status,
            "recorded_at": utc_now_iso(),
        }
        if extra:
            entry["extra"] = extra
        line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        self._index.setdefault(day, [])
        if content_hash not in self._index[day]:
            self._index[day].append(content_hash)
            self._save_index()
        return entry

    def partitions(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._index.items()}

    def replace_index(self, new_index: dict[str, list[str]]) -> None:
        """Replace partition index after retention prune (manifest JSONL remains append-only)."""
        self._index = {k: list(v) for k, v in new_index.items()}
        self._save_index()

    def list_entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def digest(self) -> str:
        return sha_obj({"partitions": self.partitions(), "entry_count": len(self.list_entries())})
