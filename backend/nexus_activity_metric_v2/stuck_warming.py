"""Stuck-warming readiness helpers for activity metric qualification runners."""
from __future__ import annotations

from typing import Any


def build_readiness_row(
    *,
    symbol: str,
    activity_state: str,
    tracking_started_at: int,
    required_window_ms: int,
    coverage_ms: int,
    last_trade_ts: int | None,
    hybrid_proof: Any = None,
    quality_state: str | None = None,
    reasons: list[str] | None = None,
    checkpoint_present: bool = False,
    now_ms: int,
) -> dict[str, Any]:
    wall = max(0, int(now_ms) - int(tracking_started_at))
    coverage_ratio = float(coverage_ms) / float(required_window_ms) if required_window_ms > 0 else 0.0
    stuck = activity_state == "ACTIVITY_WARMING" and coverage_ratio < 0.98
    return {
        "symbol": symbol,
        "activity_state": activity_state,
        "coverage_ms": int(coverage_ms),
        "coverage_ratio": round(coverage_ratio, 6),
        "required_window_ms": int(required_window_ms),
        "wall_elapsed_ms": wall,
        "last_trade_ts": last_trade_ts,
        "hybrid_proof": hybrid_proof,
        "quality_state": quality_state,
        "reasons": list(reasons or []),
        "checkpoint_present": bool(checkpoint_present),
        "stuck_warming": {
            "stuck_warming": stuck,
            "stuck_warming_class": "WARMING" if stuck else "READY",
            "stuck_warming_detail": None,
        },
        "blocker": None,
    }


def summarize_readiness(rows: list[dict[str, Any]], *, tracking: int) -> dict[str, Any]:
    ready = sum(1 for r in rows if r.get("activity_state") == "ACTIVITY_READY")
    warming = sum(1 for r in rows if r.get("activity_state") == "ACTIVITY_WARMING")
    stale = sum(1 for r in rows if (r.get("stuck_warming") or {}).get("stuck_warming_class") == "STALE_DATA")
    ratios = [float(r.get("coverage_ratio") or 0.0) for r in rows]
    median = sorted(ratios)[len(ratios) // 2] if ratios else 0.0
    classes: dict[str, int] = {}
    for r in rows:
        cls = (r.get("stuck_warming") or {}).get("stuck_warming_class") or "UNKNOWN"
        classes[cls] = classes.get(cls, 0) + 1
    return {
        "tracking": tracking,
        "ready": ready,
        "warming": warming,
        "stale": stale,
        "median_coverage": median,
        "stuck_warming_by_class": classes,
    }
