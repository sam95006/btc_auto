"""V14-B Event Study Engine — symbol and regime grouping."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from backend.nexus_event_study.constants import DEFAULT_MIN_EVENTS_PER_GROUP
from backend.nexus_event_study.types import StudyEvent


def group_by_symbol(events: Iterable[StudyEvent]) -> dict[str, list[StudyEvent]]:
    out: dict[str, list[StudyEvent]] = defaultdict(list)
    for e in events:
        out[e.symbol].append(e)
    return dict(out)


def group_by_regime(events: Iterable[StudyEvent]) -> dict[str, list[StudyEvent]]:
    out: dict[str, list[StudyEvent]] = defaultdict(list)
    for e in events:
        out[e.regime].append(e)
    return dict(out)


def group_by_symbol_regime(events: Iterable[StudyEvent]) -> dict[tuple[str, str], list[StudyEvent]]:
    out: dict[tuple[str, str], list[StudyEvent]] = defaultdict(list)
    for e in events:
        out[(e.symbol, e.regime)].append(e)
    return dict(out)


def summarize_groups(
    events: Iterable[StudyEvent],
    *,
    min_events: int = DEFAULT_MIN_EVENTS_PER_GROUP,
) -> dict[str, Any]:
    by_sym = group_by_symbol(events)
    by_reg = group_by_regime(events)
    by_both = group_by_symbol_regime(events)
    return {
        "schema": "v14_b_grouping_summary",
        "symbol_groups": {k: len(v) for k, v in sorted(by_sym.items())},
        "regime_groups": {k: len(v) for k, v in sorted(by_reg.items())},
        "symbol_regime_groups": {
            f"{a}|{b}": len(v) for (a, b), v in sorted(by_both.items())
        },
        "eligible_symbol_groups": {
            k: len(v) for k, v in sorted(by_sym.items()) if len(v) >= min_events
        },
        "eligible_regime_groups": {
            k: len(v) for k, v in sorted(by_reg.items()) if len(v) >= min_events
        },
        "min_events_per_group": min_events,
        "total_events": sum(len(v) for v in by_sym.values()),
    }
