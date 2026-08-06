"""Point-in-time observation selectors — refuse future / current substitution."""
from __future__ import annotations

from typing import Any, Callable, TypeVar

T = TypeVar("T")


class PitObservationError(ValueError):
    """Fail-closed when an observation leaks across time."""


def _latest_at_or_before(
    rows: list[dict[str, Any]],
    *,
    as_of_ms: int,
    time_key: str,
) -> dict[str, Any] | None:
    eligible = [r for r in rows if int(r[time_key]) <= int(as_of_ms)]
    if not eligible:
        return None
    return max(eligible, key=lambda r: int(r[time_key]))


def select_spec_at(instrument: dict[str, Any], *, as_of_ms: int) -> dict[str, Any] | None:
    return _latest_at_or_before(
        list(instrument.get("spec_timeline") or []),
        as_of_ms=as_of_ms,
        time_key="effective_ms",
    )


def select_liquidity_at(instrument: dict[str, Any], *, as_of_ms: int) -> dict[str, Any] | None:
    return _latest_at_or_before(
        list(instrument.get("liquidity_observations") or []),
        as_of_ms=as_of_ms,
        time_key="observation_ms",
    )


def select_tradable_at(instrument: dict[str, Any], *, as_of_ms: int) -> dict[str, Any] | None:
    return _latest_at_or_before(
        list(instrument.get("tradable_states") or []),
        as_of_ms=as_of_ms,
        time_key="effective_ms",
    )


def select_completeness_at(instrument: dict[str, Any], *, as_of_ms: int) -> dict[str, Any] | None:
    return _latest_at_or_before(
        list(instrument.get("data_completeness_observations") or []),
        as_of_ms=as_of_ms,
        time_key="observation_ms",
    )


def assert_observation_not_from_future(
    *,
    observation_ms: int | None,
    as_of_ms: int,
    field: str,
) -> None:
    if observation_ms is None:
        return
    if int(observation_ms) > int(as_of_ms):
        raise PitObservationError(f"future_observation_leak:{field}:{observation_ms}>{as_of_ms}")


def classify_listing_state(instrument: dict[str, Any], *, as_of_ms: int) -> str:
    """Return one of: NOT_YET_LISTED | LISTED | DELISTED."""
    listing = int(instrument["listing_ms"])
    delisting = instrument.get("delisting_ms")
    if listing > int(as_of_ms):
        return "NOT_YET_LISTED"
    if delisting is not None and int(delisting) <= int(as_of_ms):
        return "DELISTED"
    return "LISTED"


def coin_exists_at(instrument: dict[str, Any], *, as_of_ms: int) -> bool:
    exists_from = instrument.get("coin_exists_from_ms")
    if exists_from is None:
        exists_from = instrument["listing_ms"]
    return int(exists_from) <= int(as_of_ms)


def map_pit(
    instruments: list[dict[str, Any]],
    *,
    as_of_ms: int,
    selector: Callable[[dict[str, Any]], T | None],
) -> dict[str, T]:
    out: dict[str, T] = {}
    for row in instruments:
        val = selector(row)
        if val is not None:
            out[str(row["symbol"])] = val
    return out
