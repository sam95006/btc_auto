"""Point-in-time data foundation for offline research qualification.

This module is read-only by design: it contains timestamp contracts, dataset
quality labels, and preregistered microstructure policies. It does not place
orders, start sessions, mutate runtime state, or qualify Structural Geometry.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.nexus_demo_execution.geometry_contracts import CandidateEvidence
from backend.nexus_demo_execution.historical_market_data import Candle, interval_ms
from backend.nexus_demo_execution.session_limits import (
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
    TAKER_FEE_RATE_DEFAULT,
)

CANONICAL_TIMESTAMP_UNIT = "milliseconds"
CANONICAL_TIMEZONE = "UTC"
PARTIAL_CANDLE_ALLOWED = False
STRUCTURAL_LIQUIDITY_LABEL = "STRUCTURAL_LIQUIDITY_PROXY"
CURRENT_LIQUIDITY_CLAIMED_AS_ORDERBOOK = False

DATA_QUALITY_LABELS = frozenset(
    {
        "PIT_COMPLETE",
        "PIT_PARTIAL",
        "PIT_GAPS_PRESENT",
        "CURRENT_ONLY_METADATA",
        "CONSERVATIVE_POLICY_ASSUMPTION",
        "UNAVAILABLE",
        "INVALID_SAMPLE",
    }
)

SPREAD_POLICY = (
    "REAL_HISTORICAL_BID_ASK",
    "OHLCV_CONSERVATIVE_SPREAD_PROXY",
    "FIXED_CONSERVATIVE_BPS_BY_LIQUIDITY_TIER",
    "INVALID_SAMPLE",
)
SLIPPAGE_POLICY = (
    "FIXED_CONSERVATIVE_BPS_BY_LIQUIDITY_TIER",
    "ADVERSE_STRESS_MULTIPLIER",
    "INVALID_SAMPLE",
)
QUALIFICATION_FEE_SOURCE = "STATIC_CONSERVATIVE_POLICY_ASSUMPTION"
SYMBOL_STATUS_PIT_PARTIAL = "SYMBOL_STATUS_PIT=PARTIAL"
SURVIVORSHIP_BIAS_RISK_HIGH = "HIGH"


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FundingRecord:
    symbol: str
    funding_rate: float
    funding_ts_ms: int
    source: str = "BYBIT_DEMO_PUBLIC"
    source_endpoint: str = "/v5/market/funding/history"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_candidate_field_asof(candidate: CandidateEvidence) -> ValidationResult:
    """Fail closed when a PIT feature is newer than the decision timestamp."""
    if candidate.decision_ts_ms is None:
        return ValidationResult(False, "decision_ts_ms_missing")
    future = {
        field: ts
        for field, ts in (candidate.field_asof_ts_ms or {}).items()
        if int(ts) > int(candidate.decision_ts_ms)
    }
    if future:
        return ValidationResult(False, "future_feature_asof_ts", {"future_fields": sorted(future)})
    return ValidationResult(True, "pit_feature_asof_valid")


def validate_closed_bar_decision(
    *,
    decision_ts_ms: int,
    feature_bars: list[Candle],
    interval: str,
    fixture_mode: bool = False,
) -> ValidationResult:
    """Enforce fully closed feature bars for canonical qualification."""
    if not feature_bars:
        return ValidationResult(False, "feature_bars_missing")
    step = interval_ms(interval)
    for bar in feature_bars:
        close_ts = bar.close_ts_ms if bar.close_ts_ms is not None else bar.open_ts_ms + step
        if close_ts > decision_ts_ms:
            return ValidationResult(False, "partial_or_future_feature_bar", {"bar_open_ts_ms": bar.open_ts_ms})
    last = feature_bars[-1]
    last_close = last.close_ts_ms if last.close_ts_ms is not None else last.open_ts_ms + step
    if not fixture_mode and int(decision_ts_ms) != int(last_close):
        return ValidationResult(False, "decision_ts_must_equal_last_feature_bar_close")
    return ValidationResult(True, "closed_bar_contract_valid")


def validate_outcome_after_decision(
    *,
    decision_ts_ms: int,
    outcome_bars: list[Candle],
    interval: str,
) -> ValidationResult:
    """Outcome candles must start at the next legal timestamp and close after T."""
    step = interval_ms(interval)
    for bar in outcome_bars:
        close_ts = bar.close_ts_ms if bar.close_ts_ms is not None else bar.open_ts_ms + step
        if bar.open_ts_ms < decision_ts_ms or close_ts <= decision_ts_ms:
            return ValidationResult(False, "lookahead_outcome_candle", {"bar_open_ts_ms": bar.open_ts_ms})
    return ValidationResult(True, "outcome_after_decision_valid")


def funding_records_for_decision(
    records: list[FundingRecord],
    *,
    decision_ts_ms: int,
) -> tuple[FundingRecord | None, ValidationResult]:
    """Return the latest published/effective funding record known at decision T."""
    eligible = [r for r in records if int(r.funding_ts_ms) <= int(decision_ts_ms)]
    future = [r for r in records if int(r.funding_ts_ms) > int(decision_ts_ms)]
    if future and not eligible:
        return None, ValidationResult(False, "future_funding_leakage_rejected")
    latest = max(eligible, key=lambda r: r.funding_ts_ms) if eligible else None
    return latest, ValidationResult(True, "funding_context_pit_valid")


def realized_funding_cost(
    *,
    notional: float,
    entry_ts_ms: int,
    exit_ts_ms: int,
    records: list[FundingRecord],
) -> float:
    """Count only funding events crossed while the position is open."""
    crossed = [r for r in records if int(entry_ts_ms) < int(r.funding_ts_ms) <= int(exit_ts_ms)]
    return sum(abs(float(notional)) * float(r.funding_rate) for r in crossed)


def metadata_status_for_historical_replay(*, has_pit_history: bool) -> str:
    return "PIT_COMPLETE" if has_pit_history else "CURRENT_ONLY_METADATA"


def survivorship_bias_guard(*, symbol_status_pit_proven: bool) -> dict[str, str]:
    if symbol_status_pit_proven:
        return {"SYMBOL_STATUS_PIT": "PIT_COMPLETE", "SURVIVORSHIP_BIAS_RISK": "PARTIAL"}
    return {"SYMBOL_STATUS_PIT": "PARTIAL", "SURVIVORSHIP_BIAS_RISK": SURVIVORSHIP_BIAS_RISK_HIGH}


def spread_policy_for_replay(*, historical_bid_ask_available: bool) -> dict[str, Any]:
    source = SPREAD_POLICY[0] if historical_bid_ask_available else SPREAD_POLICY[2]
    return {
        "source": source,
        "hierarchy": list(SPREAD_POLICY),
        "performance_dependent_selection": False,
    }


def slippage_policy_for_replay() -> dict[str, Any]:
    return {
        "source": SLIPPAGE_POLICY[0],
        "hierarchy": list(SLIPPAGE_POLICY),
        "performance_dependent_selection": False,
    }


def fee_policy_for_qualification() -> dict[str, Any]:
    return {
        "source": QUALIFICATION_FEE_SOURCE,
        "taker_fee_rate": TAKER_FEE_RATE_DEFAULT,
        "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
        "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        "cost_thresholds_changed": False,
    }
