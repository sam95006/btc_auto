"""V14-B Event Study Engine — missing-event handling."""
from __future__ import annotations

from typing import Any, Iterable

from backend.nexus_event_study.definitions import require_definition
from backend.nexus_event_study.types import StudyEvent


MISSING_REASONS = (
    "missing_required_field",
    "invalid_timestamps",
    "not_yet_available_pit",
    "incomplete_forward_path",
    "overlap_exclusion",
    "unknown_event_definition",
    "zero_entry_price",
    "empty_cohort",
)


def validate_event_fields(event: StudyEvent) -> list[str]:
    reasons: list[str] = []
    try:
        defn = require_definition(event.event_id)
    except KeyError:
        return ["unknown_event_definition"]
    payload = event.payload or {}
    for field in defn.required_fields:
        # Core StudyEvent fields cover some; payload for the rest.
        if field in {
            "symbol",
            "side",
            "exchange_ts_ms",
            "receive_ts_ms",
        }:
            continue
        if field not in payload or payload.get(field) is None:
            reasons.append("missing_required_field")
            break
    if event.exchange_ts_ms <= 0 or event.receive_ts_ms <= 0:
        reasons.append("invalid_timestamps")
    if event.entry_price <= 0:
        reasons.append("zero_entry_price")
    return reasons


def classify_missing(
    events: Iterable[StudyEvent],
    *,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    """Partition into valid vs missing with explicit reasons — never silent impute."""
    valid: list[StudyEvent] = []
    missing: list[dict[str, Any]] = []
    for e in events:
        reasons = validate_event_fields(e)
        if as_of_ms is not None:
            if e.exchange_ts_ms > as_of_ms or e.receive_ts_ms > as_of_ms:
                reasons.append("not_yet_available_pit")
        if reasons:
            missing.append(
                {
                    "observation_id": e.observation_id,
                    "event_id": e.event_id,
                    "reasons": reasons,
                    "policy": "EXCLUDE_WITH_REASON",
                }
            )
        else:
            valid.append(e)
    return {
        "schema": "v14_b_missing_event_handling",
        "valid_count": len(valid),
        "missing_count": len(missing),
        "valid": valid,
        "missing": missing,
        "silent_impute": False,
        "known_reasons": list(MISSING_REASONS),
    }
