"""Future-data exclusion and development-interval guards for V13-F."""
from __future__ import annotations

from typing import Any


def assert_future_data_excluded(
    *,
    proposed_start_ms: int,
    proposed_end_ms: int,
    as_of_ms: int,
) -> dict[str, Any]:
    """Fail-closed: any interval extending past as_of is excluded."""
    future_touch = proposed_end_ms > as_of_ms
    return {
        "status": "FUTURE_DATA_EXCLUDED" if not future_touch else "FUTURE_DATA_VIOLATION",
        "proposed_start_ms": int(proposed_start_ms),
        "proposed_end_ms": int(proposed_end_ms),
        "as_of_ms": int(as_of_ms),
        "future_data_excluded": not future_touch,
        "allowed": not future_touch,
    }


def prove_candidate_development_intervals(
    candidates: list[dict[str, Any]],
    *,
    as_of_ms: int,
) -> dict[str, Any]:
    """Every candidate development interval must exclude future data."""
    results: list[dict[str, Any]] = []
    all_ok = True
    for cand in candidates:
        interval = cand.get("development_interval") or {}
        proof = assert_future_data_excluded(
            proposed_start_ms=int(interval.get("start_ms") or 0),
            proposed_end_ms=int(interval.get("end_ms") or 0),
            as_of_ms=as_of_ms,
        )
        proof["candidate_id"] = cand.get("candidate_id")
        results.append(proof)
        if not proof["allowed"]:
            all_ok = False
    return {
        "status": "ALL_DEVELOPMENT_INTERVALS_EXCLUDE_FUTURE" if all_ok else "FUTURE_DATA_VIOLATION",
        "all_excluded": all_ok,
        "results": results,
    }


def prove_market_universe_pit(market: dict[str, Any]) -> dict[str, Any]:
    """Eligible universe must not include instruments listed after as_of."""
    as_of = int(market.get("as_of_ms") or 0)
    violations: list[str] = []
    for e in market.get("eligible_universe") or []:
        if int(e.get("listing_timestamp_ms") or 0) > as_of:
            violations.append(str(e.get("symbol")))
    return {
        "status": "UNIVERSE_PIT_OK" if not violations else "UNIVERSE_PIT_VIOLATION",
        "ok": len(violations) == 0,
        "violations": violations,
        "as_of_ms": as_of,
        "universe_checksum": market.get("universe_checksum"),
    }
