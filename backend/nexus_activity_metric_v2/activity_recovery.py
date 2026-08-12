"""Activity checkpoint inspection + freshness publication classification.

Used by historical activity-metric runners and V30 production cycle recovery.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_activity_metric_v2.constants import DEFAULT_STALE_MS, DEFAULT_WINDOW_MS

FRESHNESS_CLOCK_CHAIN: tuple[str, ...] = (
    "raw_ws_event_ts",
    "checkpoint_ts",
    "publisher_state_ts",
    "gate_eval_ts",
)


def _last_event_ts_ms(raw: dict[str, Any]) -> int | None:
    events = raw.get("events") or []
    for ev in reversed(events):
        if isinstance(ev, dict):
            ts = ev.get("ts_ms") or ev.get("timestamp_ms") or ev.get("T")
            if ts is not None:
                return int(ts)
        elif isinstance(ev, (list, tuple)) and ev:
            try:
                return int(ev[0])
            except (TypeError, ValueError):
                continue
    stats = raw.get("stats") or {}
    for key in ("last_trade_ts_ms", "last_event_ts_ms", "last_ts_ms"):
        if stats.get(key) is not None:
            return int(stats[key])
    return None


def inspect_checkpoint(path: Path, *, now_ms: int) -> dict[str, Any]:
    """Inspect one symbol activity checkpoint — no secrets."""
    out: dict[str, Any] = {
        "present": path.exists(),
        "exists": path.exists(),
        "source": None,
        "last_trade_ts": None,
        "last_trade_age_ms": None,
        "coverage_ms": 0,
        "stale": True,
    }
    if not path.exists():
        return out
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        last_ts = _last_event_ts_ms(raw)
        if last_ts is None:
            last_ts = int(path.stat().st_mtime * 1000)
        age = float(max(0, now_ms - int(last_ts)))
        window_ms = int(raw.get("window_ms") or DEFAULT_WINDOW_MS)
        stats = raw.get("stats") or {}
        coverage = int(stats.get("coverage_ms") or stats.get("window_coverage_ms") or 0)
        if coverage <= 0 and not out["stale"]:
            coverage = min(window_ms, int(max(0, window_ms - age)))
        out.update(
            {
                "source": str(raw.get("source") or "checkpoint"),
                "last_trade_ts": int(last_ts),
                "last_trade_age_ms": age,
                "coverage_ms": coverage,
                "stale": age > float(DEFAULT_STALE_MS),
                "window_ms": window_ms,
            }
        )
    except Exception:  # noqa: BLE001
        out["source"] = "checkpoint_read_error"
        out["stale"] = True
    return out


def classify_freshness_publication_root(
    *,
    published_freshness_ts_ms: int | None,
    checkpoint_ts_ms: int | None,
    gate_eval_ts_ms: int,
    ws_live: bool,
    sidecar_ignored_publisher_stale: bool,
    raw_ws_event_ts_ms: int | None,
) -> dict[str, Any]:
    """Classify stale root cause — honest NO_NEW_TRADE vs BROKEN_PUBLISHER_REFRESH."""
    market_ts = published_freshness_ts_ms or raw_ws_event_ts_ms
    age_ms = None
    if market_ts is not None:
        age_ms = float(max(0, gate_eval_ts_ms - int(market_ts)))
    stale = age_ms is None or age_ms > float(DEFAULT_STALE_MS)
    if not stale:
        return {
            "freshness_publication_root": "FRESH",
            "stale_kind": "FRESH",
            "publication_failure_stage": None,
            "market_event_age_ms": age_ms,
            "ws_live": ws_live,
        }
    if sidecar_ignored_publisher_stale:
        root = "BROKEN_PUBLISHER_REFRESH"
        stage = "SIDECAR_IGNORED"
    elif not ws_live:
        root = "BROKEN_PUBLISHER_REFRESH"
        stage = "WS_NOT_LIVE"
    elif checkpoint_ts_ms is not None and market_ts is not None and checkpoint_ts_ms > int(market_ts):
        root = "BROKEN_PUBLISHER_REFRESH"
        stage = "CHECKPOINT_AHEAD_OF_PUBLISHER"
    else:
        root = "NO_NEW_TRADE"
        stage = "MARKET_QUIET"
    stale_kind = "BROKEN_PUBLISHER_REFRESH" if root == "BROKEN_PUBLISHER_REFRESH" else "NO_NEW_TRADE"
    return {
        "freshness_publication_root": root,
        "stale_kind": stale_kind,
        "publication_failure_stage": stage,
        "market_event_age_ms": age_ms,
        "ws_live": ws_live,
    }


def run_recovery_pass(
    symbols: list[str],
    *,
    checkpoint_root: Path,
    max_symbols: int = 192,
    ws_connected: bool = True,
    subscribed_symbols: set[str] | None = None,
    aggregator_heartbeat_age_ms: int | None = None,
    only_broken: bool = True,
    workers: int = 4,
) -> dict[str, Any]:
    """Best-effort checkpoint recovery scan — production-safe no-op when data absent."""
    _ = (subscribed_symbols, aggregator_heartbeat_age_ms, workers)
    now_ms = int(__import__("time").time() * 1000)
    inspected = 0
    recovered = 0
    still_stale = 0
    for sym in symbols[:max_symbols]:
        path = Path(checkpoint_root) / f"activity_{sym}.json"
        insp = inspect_checkpoint(path, now_ms=now_ms)
        inspected += 1
        if insp.get("stale"):
            still_stale += 1
            if not only_broken and path.exists():
                recovered += 1
        else:
            recovered += 1
    return {
        "schema": "activity_recovery_pass_v1",
        "inspected": inspected,
        "recovered": recovered,
        "still_stale": still_stale,
        "ws_connected": ws_connected,
        "only_broken": only_broken,
        "fabricated_trades": False,
    }
