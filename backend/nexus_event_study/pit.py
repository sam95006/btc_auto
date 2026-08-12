"""V14-B Event Study Engine — Point-in-Time eligibility."""
from __future__ import annotations

from typing import Any, Iterable

from backend.nexus_event_study.types import StudyEvent


def event_pit_eligible(event: StudyEvent, *, as_of_ms: int) -> bool:
    """PIT: both exchange and receive timestamps must be <= as_of_ms."""
    if event.exchange_ts_ms <= 0 or event.receive_ts_ms <= 0:
        return False
    return event.exchange_ts_ms <= as_of_ms and event.receive_ts_ms <= as_of_ms


def filter_pit(events: Iterable[StudyEvent], *, as_of_ms: int) -> list[StudyEvent]:
    return [e for e in events if event_pit_eligible(e, as_of_ms=as_of_ms)]


def pit_partition(
    events: Iterable[StudyEvent],
    *,
    as_of_ms: int,
) -> dict[str, Any]:
    eligible: list[StudyEvent] = []
    not_yet: list[StudyEvent] = []
    invalid: list[StudyEvent] = []
    for e in events:
        if e.exchange_ts_ms <= 0 or e.receive_ts_ms <= 0:
            invalid.append(e)
            continue
        if e.exchange_ts_ms <= as_of_ms and e.receive_ts_ms <= as_of_ms:
            eligible.append(e)
        elif e.exchange_ts_ms <= as_of_ms and e.receive_ts_ms > as_of_ms:
            not_yet.append(e)
        else:
            # Future exchange time relative to as_of
            not_yet.append(e)
    return {
        "schema": "v14_b_pit_partition",
        "as_of_ms": as_of_ms,
        "eligible_count": len(eligible),
        "not_yet_available_count": len(not_yet),
        "invalid_count": len(invalid),
        "eligible": eligible,
        "not_yet_available": not_yet,
        "invalid": invalid,
        "pit_rule": "exchange_ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms",
    }


def prove_pit_excludes_future(
    events: list[StudyEvent],
    *,
    as_of_ms: int,
) -> dict[str, Any]:
    """Negative proof: events with exchange/receive after as_of must be excluded."""
    part = pit_partition(events, as_of_ms=as_of_ms)
    eligible_ids = {e.observation_id for e in part["eligible"]}
    future = [
        e
        for e in events
        if e.exchange_ts_ms > as_of_ms or e.receive_ts_ms > as_of_ms
    ]
    leaked = [e.observation_id for e in future if e.observation_id in eligible_ids]
    return {
        "schema": "v14_b_pit_proof",
        "as_of_ms": as_of_ms,
        "future_event_count": len(future),
        "leaked_ids": leaked,
        "pit_holds": len(leaked) == 0,
        "eligible_count": part["eligible_count"],
    }
