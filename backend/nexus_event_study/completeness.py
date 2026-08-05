"""V14-B Event Study Engine — data completeness filters."""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from backend.nexus_event_study.constants import DEFAULT_MIN_COMPLETENESS
from backend.nexus_event_study.types import HorizonOutcome, StudyEvent


def path_completeness(price_path: Sequence[float], *, required_horizon: int) -> float:
    """Fraction of bars from 0..required_horizon that are present/finite."""
    if required_horizon <= 0:
        return 0.0
    need = required_horizon + 1  # includes entry bar
    if len(price_path) <= 0:
        return 0.0
    present = 0
    for i in range(need):
        if i >= len(price_path):
            break
        try:
            v = float(price_path[i])
        except (TypeError, ValueError):
            continue
        if v == v and v > 0:  # finite and positive
            present += 1
    return present / need


def filter_by_completeness(
    events: Iterable[StudyEvent],
    paths: dict[str, Sequence[float]],
    *,
    required_horizon: int,
    min_completeness: float = DEFAULT_MIN_COMPLETENESS,
) -> dict[str, Any]:
    kept: list[StudyEvent] = []
    dropped: list[dict[str, Any]] = []
    for ev in events:
        path = paths.get(ev.observation_id, ())
        score = path_completeness(path, required_horizon=required_horizon)
        if score >= min_completeness and len(path) > required_horizon:
            kept.append(ev)
        else:
            dropped.append(
                {
                    "observation_id": ev.observation_id,
                    "completeness": score,
                    "reason": "incomplete_forward_path",
                    "required_horizon": required_horizon,
                    "min_completeness": min_completeness,
                }
            )
    return {
        "schema": "v14_b_completeness_filter",
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "kept": kept,
        "dropped": dropped,
        "min_completeness": min_completeness,
        "required_horizon": required_horizon,
    }


def outcome_availability_rate(outcomes: Sequence[HorizonOutcome]) -> float:
    if not outcomes:
        return 0.0
    return sum(1 for o in outcomes if o.available) / len(outcomes)
