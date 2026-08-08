"""Bounded persistent Live Radar rank-event store (NEW/UP/DOWN/OUT).

Survives process restart via JSONL under NEXUS_DATA_DIR (or worktree runtime fallback).
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

MAX_EVENTS = 500
PREV_FILENAME = "live_radar_prev.json"
EVENTS_FILENAME = "live_radar_events.jsonl"


def _writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".nexus_radar_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def resolve_radar_data_dir() -> Path | None:
    raw = str(os.environ.get("NEXUS_DATA_DIR", "") or "").strip()
    if raw:
        root = Path(raw) / "live_radar"
        if _writable_dir(root):
            return root
    # Worktree / local runtime fallback (preview-safe, not production)
    runtime = Path(os.environ.get("NEXUS_RUNTIME_DIR", r"D:\NEXUS_RUNTIME"))
    root = runtime / "live_radar"
    if _writable_dir(root):
        return root
    return None


class RankEventStore:
    """Prev-rank map + bounded JSONL event history."""

    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        if root is not None:
            root = Path(root)
            try:
                root.mkdir(parents=True, exist_ok=True)
            except Exception:  # noqa: BLE001
                root = None
            self._root = root
        else:
            self._root = resolve_radar_data_dir()
        self._mode = "disk" if self._root is not None else "memory"
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self._prev: dict[str, dict[str, Any]] = {}
        self._load()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def root(self) -> str | None:
        return str(self._root) if self._root else None

    def _load(self) -> None:
        if self._root is None:
            return
        prev_path = self._root / PREV_FILENAME
        events_path = self._root / EVENTS_FILENAME
        try:
            if prev_path.exists():
                raw = json.loads(prev_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._prev = {str(k).upper(): v for k, v in raw.items() if isinstance(v, dict)}
        except Exception:  # noqa: BLE001
            self._prev = {}
        try:
            if events_path.exists():
                lines = events_path.read_text(encoding="utf-8").splitlines()
                for line in lines[-MAX_EVENTS:]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(ev, dict) and ev.get("id"):
                        self._events.append(ev)
        except Exception:  # noqa: BLE001
            pass

    def load_prev(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._prev.items()}

    def save_prev(self, prev: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            self._prev = {str(k).upper(): dict(v) for k, v in prev.items()}
            if self._root is None:
                return
            self._root.mkdir(parents=True, exist_ok=True)
            path = self._root / PREV_FILENAME
            tmp = self._root / (PREV_FILENAME + ".tmp")
            tmp.write_text(json.dumps(self._prev, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            tmp.replace(path)

    def append_events(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        with self._lock:
            ids = {e.get("id") for e in self._events}
            fresh = [e for e in events if e.get("id") and e.get("id") not in ids]
            if not fresh:
                return
            for e in fresh:
                self._events.appendleft(e)
            if self._root is None:
                return
            path = self._root / EVENTS_FILENAME
            with path.open("a", encoding="utf-8") as fh:
                for e in fresh:
                    fh.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._trim_jsonl(path)

    def _trim_jsonl(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) <= MAX_EVENTS * 2:
                return
            keep = lines[-MAX_EVENTS:]
            path.write_text("\n".join(keep) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    def list_events(self, *, limit: int = 50, symbol: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._events)
        if symbol:
            sym = symbol.upper()
            rows = [e for e in rows if str(e.get("symbol") or "").upper() == sym]
        return rows[: max(1, min(limit, MAX_EVENTS))]

    def clear_memory_for_tests(self) -> None:
        with self._lock:
            self._events.clear()
            self._prev.clear()
