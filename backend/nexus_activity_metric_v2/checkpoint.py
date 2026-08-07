"""Checkpoint persistence for restart recovery."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.nexus_activity_metric_v2.constants import SCHEMA, SCHEMA_VERSION
from backend.nexus_activity_metric_v2.window import RollingActivityWindow


@dataclass
class ActivityCheckpointStore:
    """Atomic JSON checkpoint store — symbol-isolated files."""

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in symbol)
        return self.root / f"activity_{safe}.json"

    def save(self, window: RollingActivityWindow, *, now_ms: int) -> Path:
        path = self._path(window.symbol)
        payload = {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "symbol": window.symbol,
            "window_ms": window.window_ms,
            "saved_at_ms": int(now_ms),
            "source": window.source,
            "warmup_achieved": bool(window._warmup_achieved),
            "stats": window.stats(),
            "events": window.export_events(),
        }
        self._atomic_write(path, payload)
        return path

    def load(
        self, symbol: str, *, now_ms: int
    ) -> RollingActivityWindow | None:
        path = self._path(symbol)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        events = list(raw.get("events") or [])
        window_ms = int(raw.get("window_ms") or 86_400_000)
        win = RollingActivityWindow.from_checkpoint_events(
            symbol,
            events,
            window_ms=window_ms,
            now_ms=now_ms,
            source=str(raw.get("source") or "checkpoint_replay"),
        )
        win._warmup_achieved = bool(raw.get("warmup_achieved", False))
        return win

    def exists(self, symbol: str) -> bool:
        return self._path(symbol).exists()

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=".activity_ckpt_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
