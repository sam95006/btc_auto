"""H3 OOS reservation maturity gate — blocks premature download/execute.

Does not download market data. Does not mutate frozen policies.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from backend.nexus_demo_execution.historical_market_data import interval_ms

# Provider publication lag after candle close before data is considered reliable.
PROVIDER_LAG_MS = {
    "15": 60_000,  # 1 minute
    "60": 120_000,  # 2 minutes
    "240": 300_000,  # 5 minutes
}

REQUIRED_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
REQUIRED_INTERVALS = ("15", "60", "240")
MAX_TIMEFRAME = "240"

STATUS_NOT_MATURE = "OOS_WINDOW_NOT_MATURE"
REASON_END_IN_FUTURE = "RESERVED_END_IS_IN_THE_FUTURE"
REASON_MAX_TF_OPEN = "MAXIMUM_TIMEFRAME_CANDLE_NOT_CLOSED"
REASON_PROVIDER_LAG = "PROVIDER_PUBLICATION_LAG_NOT_SATISFIED"
REASON_COVERAGE = "SYMBOL_TIMEFRAME_COVERAGE_INCOMPLETE"


@dataclass
class MaturityAssessment:
    reservation_id: str
    reserved_start: int
    reserved_end: int
    now_ms: int
    reservation_window_closed: bool
    maximum_timeframe_closed: bool
    provider_lag_satisfied: bool
    all_symbol_timeframe_coverage_complete: bool
    missing_interval_count: int
    expected_record_count: int
    actual_record_count: int | None
    coverage_ratio_by_symbol_timeframe: dict[str, float]
    latest_required_closed_candle_time: int
    provider_latest_available_time: int | None
    data_integrity_status: str
    status: str
    reason: str | None
    future_oos_execution_allowed: bool
    prior_founder_approval_reuse_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _latest_closed_candle_open_ms(*, now_ms: int, interval: str) -> int:
    step = interval_ms(interval)
    # Candle that contains `now` opens at floor(now/step)*step; it is closed when now >= open+step.
    open_ms = (now_ms // step) * step
    if now_ms >= open_ms + step:
        return open_ms  # current candle already closed? use its open
    # still inside open candle → last closed is previous
    return open_ms - step


def assess_reservation_maturity(
    *,
    reservation: dict[str, Any],
    now_ms: int | None = None,
    coverage_ratio_by_symbol_timeframe: dict[str, float] | None = None,
    missing_interval_count: int = 0,
    actual_record_count: int | None = None,
    provider_latest_available_time: int | None = None,
) -> MaturityAssessment:
    """Pure maturity check. Network optional via caller-supplied coverage facts."""
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    start = int(reservation["reserved_start"])
    end = int(reservation["reserved_end"])
    rid = str(reservation.get("reservation_id") or "")

    symbols = list(reservation.get("symbols") or list(REQUIRED_SYMBOLS))
    intervals = [str(x) for x in (reservation.get("intervals") or list(REQUIRED_INTERVALS))]

    expected = 0
    for _sym in symbols:
        for iv in intervals:
            step = interval_ms(iv)
            expected += max(0, int((end - start) // step))

    window_closed = now > end
    latest_closed_240 = _latest_closed_candle_open_ms(now_ms=now, interval=MAX_TIMEFRAME)
    # The 240m candle that includes reserved_end opens at floor(end/step)*step and closes at open+step.
    step_240 = interval_ms(MAX_TIMEFRAME)
    end_candle_open = (end // step_240) * step_240
    end_candle_close = end_candle_open + step_240
    max_tf_closed = now >= end_candle_close
    lag = PROVIDER_LAG_MS.get(MAX_TIMEFRAME, 300_000)
    provider_lag_ok = now >= (end_candle_close + lag)

    coverage = dict(coverage_ratio_by_symbol_timeframe or {})
    # Without measured coverage, do not claim complete.
    if coverage:
        coverage_complete = all(
            float(coverage.get(f"{s}_{iv}", 0.0)) >= 0.999
            for s in symbols
            for iv in intervals
        ) and int(missing_interval_count) == 0
    else:
        coverage_complete = False

    integrity = "PASS" if (
        window_closed and max_tf_closed and provider_lag_ok and coverage_complete and missing_interval_count == 0
    ) else "FAIL"

    reason = None
    status = "OOS_WINDOW_MATURE"
    if not window_closed:
        status = STATUS_NOT_MATURE
        reason = REASON_END_IN_FUTURE
    elif not max_tf_closed:
        status = STATUS_NOT_MATURE
        reason = REASON_MAX_TF_OPEN
    elif not provider_lag_ok:
        status = STATUS_NOT_MATURE
        reason = REASON_PROVIDER_LAG
    elif not coverage_complete:
        status = STATUS_NOT_MATURE
        reason = REASON_COVERAGE

    allowed = status == "OOS_WINDOW_MATURE" and integrity == "PASS"

    return MaturityAssessment(
        reservation_id=rid,
        reserved_start=start,
        reserved_end=end,
        now_ms=now,
        reservation_window_closed=window_closed,
        maximum_timeframe_closed=max_tf_closed,
        provider_lag_satisfied=provider_lag_ok,
        all_symbol_timeframe_coverage_complete=coverage_complete,
        missing_interval_count=int(missing_interval_count),
        expected_record_count=expected,
        actual_record_count=actual_record_count,
        coverage_ratio_by_symbol_timeframe=coverage,
        latest_required_closed_candle_time=latest_closed_240,
        provider_latest_available_time=provider_latest_available_time,
        data_integrity_status=integrity,
        status=status,
        reason=reason,
        future_oos_execution_allowed=allowed,
        # Prior Founder approval for the premature attempt is exhausted and must not auto-reuse.
        prior_founder_approval_reuse_allowed=False,
    )


def assert_not_using_partial_oos_in_research(path_hint: str) -> None:
    """Hard refuse if a caller tries to point research at the sealed partial OOS cache."""
    norm = path_hint.replace("\\", "/").lower()
    if "oos_h3_untouched_v1_reserved" in norm and (
        "market_cache" in norm or "micro_cache" in norm or "/oos/" in norm
    ):
        raise RuntimeError(
            "PRELIMINARY_PARTIAL_NOT_FOR_ANALYSIS: sealed partial OOS cache forbidden in research pipeline"
        )
