"""Public-safe Market Summary History (~5m resolution, 24h–7d retention).

Persists ONLY real scanner/radar snapshot fields. Never invents points.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from backend.market.live_radar.rank_event_store import resolve_radar_data_dir

HISTORY_FILENAME = "market_summary_history.jsonl"
INTERVAL_MS = 5 * 60 * 1000
RETENTION_MS = 7 * 24 * 60 * 60 * 1000
MAX_POINTS = 2200  # ~7d @ 5m


def derive_regime_label(breadth: dict[str, Any] | None, symbol_count: int | None) -> str:
    b = breadth or {}
    insuff = int(b.get("insufficient") or 0)
    sym = int(symbol_count or 0)
    if sym > 0 and insuff >= max(1, int(sym * 0.7)):
        return "資料累積中"
    rising = int(b.get("rising") or 0)
    falling = int(b.get("falling") or 0)
    neutral = int(b.get("neutral") or 0)
    ready = rising + falling + neutral
    if ready < 8:
        return "資料累積中"
    if rising + falling < 6:
        return "低動能"
    if rising > falling * 1.25:
        return "偏多"
    if falling > rising * 1.25:
        return "偏空"
    return "多空混合"


class MarketSummaryHistoryStore:
    """Bounded JSONL history of public market-state snapshots."""

    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        if root is not None:
            try:
                root = Path(root)
                root.mkdir(parents=True, exist_ok=True)
            except Exception:  # noqa: BLE001
                root = None
            self._root = root
        else:
            self._root = resolve_radar_data_dir()
        self._mode = "disk" if self._root is not None else "memory"
        self._points: deque[dict[str, Any]] = deque(maxlen=MAX_POINTS)
        self._last_record_at = 0
        self._load()

    @property
    def mode(self) -> str:
        return self._mode

    def _path(self) -> Path | None:
        return (self._root / HISTORY_FILENAME) if self._root else None

    def _load(self) -> None:
        path = self._path()
        if path is None or not path.exists():
            return
        try:
            cutoff = int(time.time() * 1000) - RETENTION_MS
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in lines[-MAX_POINTS:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    pt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(pt, dict) and int(pt.get("timestamp") or 0) >= cutoff:
                    self._points.append(pt)
            if self._points:
                self._last_record_at = int(self._points[-1].get("timestamp") or 0)
        except Exception:  # noqa: BLE001
            pass

    def maybe_record(self, point: dict[str, Any], *, force: bool = False) -> bool:
        """Append one real snapshot if INTERVAL elapsed (or force). Returns True if written."""
        ts = int(point.get("timestamp") or time.time() * 1000)
        with self._lock:
            if not force and self._last_record_at and (ts - self._last_record_at) < INTERVAL_MS:
                return False
            # Refuse empty fabricated shells — require at least breadth OR radar count present.
            has_breadth = any(k in point for k in ("rising", "falling", "neutral"))
            has_radar = point.get("radar_eligible_count") is not None
            if not has_breadth and not has_radar:
                return False
            clean = {
                "timestamp": ts,
                "rising": int(point.get("rising") or 0),
                "neutral": int(point.get("neutral") or 0),
                "falling": int(point.get("falling") or 0),
                "insufficient": int(point.get("insufficient") or 0),
                "regime": str(point.get("regime") or "資料累積中"),
                "market_risk": int(point["market_risk"]) if point.get("market_risk") is not None else None,
                "scanner_count": int(point.get("scanner_count") or 0),
                "radar_count": int(point.get("radar_count") or point.get("radar_eligible_count") or 0),
                "trade_count": int(point.get("trade_count") or 0),
                "qualified_count": int(point.get("qualified_count") or 0),
                "radar_eligible_count": int(point.get("radar_eligible_count") or 0),
                "events_new": int(point.get("events_new") or 0),
                "events_up": int(point.get("events_up") or 0),
                "events_down": int(point.get("events_down") or 0),
                "events_out": int(point.get("events_out") or 0),
                "fabricated": False,
            }
            self._points.append(clean)
            self._last_record_at = ts
            path = self._path()
            if path is not None:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(clean, ensure_ascii=False, separators=(",", ":")) + "\n")
                    self._trim_file(path)
                except Exception:  # noqa: BLE001
                    pass
            return True

    def _trim_file(self, path: Path) -> None:
        try:
            cutoff = int(time.time() * 1000) - RETENTION_MS
            lines = path.read_text(encoding="utf-8").splitlines()
            kept = []
            for line in lines:
                try:
                    pt = json.loads(line)
                    if int(pt.get("timestamp") or 0) >= cutoff:
                        kept.append(line)
                except json.JSONDecodeError:
                    continue
            kept = kept[-MAX_POINTS:]
            tmp = path.with_suffix(".tmp")
            tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
            tmp.replace(path)
        except Exception:  # noqa: BLE001
            pass

    def list_points(self, *, hours: float = 24.0, limit: int = 400) -> list[dict[str, Any]]:
        hours = max(1.0, min(float(hours or 24), 168.0))
        lim = max(1, min(int(limit or 400), MAX_POINTS))
        cutoff = int(time.time() * 1000) - int(hours * 3600 * 1000)
        with self._lock:
            pts = [dict(p) for p in self._points if int(p.get("timestamp") or 0) >= cutoff]
        return pts[-lim:]

    def public_history(self, *, hours: float = 24.0, limit: int = 400) -> dict[str, Any]:
        points = self.list_points(hours=hours, limit=limit)
        return {
            "ok": True,
            "contract": "MARKET_SUMMARY_HISTORY_V1",
            "interval_ms": INTERVAL_MS,
            "retention_ms": RETENTION_MS,
            "hours": hours,
            "count": len(points),
            "points": points,
            "fabricated_visual_count": 0,
            "history_authority": "SERVER",
            "store_mode": self._mode,
            "member_execution": 0,
            "cache": "no-store",
        }


_HISTORY: MarketSummaryHistoryStore | None = None
_HIST_LOCK = threading.Lock()


def get_market_summary_history() -> MarketSummaryHistoryStore:
    global _HISTORY
    with _HIST_LOCK:
        if _HISTORY is None:
            _HISTORY = MarketSummaryHistoryStore()
        return _HISTORY
