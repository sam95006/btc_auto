"""V14-B Event Study Engine — overlap exclusion."""
from __future__ import annotations

from typing import Any, Iterable

from backend.nexus_event_study.definitions import require_definition
from backend.nexus_event_study.types import StudyEvent
from backend.nexus_event_study.windows import BAR_MS, build_windows


def exclude_overlapping(
    events: Iterable[StudyEvent],
    *,
    bar_ms: int = BAR_MS,
    exclusion_bars: int | None = None,
) -> dict[str, Any]:
    """Greedy chronological overlap exclusion within each (symbol, event_id).

    Keeps earlier events; drops later events whose decision falls inside the
    prior event's post window expanded by overlap_exclusion_bars.
    """
    ordered = sorted(
        events,
        key=lambda e: (e.symbol, e.event_id, e.decision_ts_ms, e.observation_id),
    )
    kept: list[StudyEvent] = []
    excluded: list[dict[str, Any]] = []
    last_by_key: dict[tuple[str, str], StudyEvent] = {}

    for ev in ordered:
        defn = require_definition(ev.event_id)
        excl = int(exclusion_bars if exclusion_bars is not None else defn.overlap_exclusion_bars)
        key = (ev.symbol, ev.event_id)
        prev = last_by_key.get(key)
        if prev is not None:
            prev_win = build_windows(prev, bar_ms=bar_ms)
            # Protect zone: post end + exclusion bars
            protect_end = int(prev_win.post.end_ts_ms or prev.decision_ts_ms) + excl * bar_ms
            if prev.decision_ts_ms <= ev.decision_ts_ms < protect_end:
                excluded.append(
                    {
                        "observation_id": ev.observation_id,
                        "reason": "overlap_exclusion",
                        "conflicts_with": prev.observation_id,
                        "protect_end_ts_ms": protect_end,
                    }
                )
                continue
        kept.append(ev)
        last_by_key[key] = ev

    return {
        "schema": "v14_b_overlap_exclusion",
        "input_count": len(ordered),
        "kept_count": len(kept),
        "excluded_count": len(excluded),
        "kept": kept,
        "excluded": excluded,
    }
