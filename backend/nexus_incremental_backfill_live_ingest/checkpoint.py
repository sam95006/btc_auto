"""Resume checkpoint contract for incremental / live ingest."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.nexus_incremental_backfill_live_ingest.constants import SCHEMA_CHECKPOINT
from backend.nexus_incremental_backfill_live_ingest.hashing import utc_now_iso


class ResumeCheckpoint:
    """Durable resume cursor: symbol → last exchange timestamp + content hash."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema": SCHEMA_CHECKPOINT,
                "cursors": {},
                "source_offset": -1,
                "last_content_hash": None,
                "updated_at": None,
            }
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self._state["schema"] = SCHEMA_CHECKPOINT
        self._state["updated_at"] = utc_now_iso()
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(self._state, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def write(
        self,
        *,
        symbol: str,
        exchange_timestamp: str,
        content_hash: str,
        source_offset: int,
        data_class: str,
        mode: str,
    ) -> dict[str, Any]:
        cursors = dict(self._state.get("cursors") or {})
        cursors[symbol] = {
            "exchange_timestamp": exchange_timestamp,
            "content_hash": content_hash,
            "data_class": data_class,
            "mode": mode,
        }
        self._state["cursors"] = cursors
        self._state["source_offset"] = int(source_offset)
        self._state["last_content_hash"] = content_hash
        self._save()
        return self.read()

    def read(self) -> dict[str, Any]:
        return dict(self._state)

    def resume_offset(self) -> int:
        return int(self._state.get("source_offset", -1)) + 1

    def cursor_for(self, symbol: str) -> dict[str, Any] | None:
        cursors = self._state.get("cursors") or {}
        cur = cursors.get(symbol)
        return dict(cur) if cur else None
