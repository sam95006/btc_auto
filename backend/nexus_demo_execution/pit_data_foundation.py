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
PIT_HISTORICAL_MARKET_DATA = "PIT_HISTORICAL_MARKET_DATA"
DERIVED_FROM_PIT_BARS = "DERIVED_FROM_PIT_BARS"
STATIC_CONSERVATIVE_POLICY_ASSUMPTION = "STATIC_CONSERVATIVE_POLICY_ASSUMPTION"
CURRENT_ONLY_METADATA = "CURRENT_ONLY_METADATA"
UNAVAILABLE = "UNAVAILABLE"

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
SOURCE_CLASSES = frozenset(
    {
        PIT_HISTORICAL_MARKET_DATA,
        DERIVED_FROM_PIT_BARS,
        STATIC_CONSERVATIVE_POLICY_ASSUMPTION,
        CURRENT_ONLY_METADATA,
        UNAVAILABLE,
    }
)
LEGACY_AMBIGUOUS_PROVENANCE_SOURCE = "PIT_HISTORICAL_MARKET_DATA" + "_OR_STATIC_POLICY"
DEFAULT_REQUIRED_PIT_FIELDS = frozenset(
    {
        "entry_price",
        "atr",
        "recent_swing_high",
        "recent_swing_low",
        "support",
        "resistance",
        "liquidity_levels",
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
    """Fail closed for dishonest PIT qualification provenance.

    This is qualification-specific validation. Legacy CandidateEvidence
    construction remains backwards compatible, but a research qualification run
    must explicitly classify market data, derived fields, policy assumptions,
    current-only metadata, and unavailable inputs.
    """
    return validate_candidate_provenance(
        candidate,
        required_pit_fields=DEFAULT_REQUIRED_PIT_FIELDS,
    )


def validate_candidate_provenance(
    candidate: CandidateEvidence,
    *,
    required_pit_fields: frozenset[str] | set[str] | tuple[str, ...] = DEFAULT_REQUIRED_PIT_FIELDS,
    allowed_policy_fields: frozenset[str] | set[str] | tuple[str, ...] = (
        "spread_bps",
        "slippage_bps",
        "fee_rate",
        "funding_rate",
        "qty",
    ),
) -> ValidationResult:
    if candidate.decision_ts_ms is None:
        return ValidationResult(False, "decision_ts_ms_missing")
    sources = candidate.field_sources or {}
    asof = candidate.field_asof_ts_ms or {}
    ambiguous = {
        field: source
        for field, source in sources.items()
        if source == LEGACY_AMBIGUOUS_PROVENANCE_SOURCE
    }
    if ambiguous:
        return ValidationResult(False, "ambiguous_provenance_source", {"fields": sorted(ambiguous)})
    unknown = {field: source for field, source in sources.items() if source not in SOURCE_CLASSES}
    if unknown:
        return ValidationResult(False, "unknown_provenance_source", {"fields": sorted(unknown)})
    missing_source = [field for field in required_pit_fields if field not in sources]
    if missing_source:
        return ValidationResult(False, "required_pit_field_source_missing", {"fields": sorted(missing_source)})
    missing_asof = [
        field
        for field in required_pit_fields
        if sources.get(field) in {PIT_HISTORICAL_MARKET_DATA, DERIVED_FROM_PIT_BARS} and field not in asof
    ]
    if missing_asof:
        return ValidationResult(False, "required_pit_field_asof_missing", {"fields": sorted(missing_asof)})
    unavailable_required = [field for field in required_pit_fields if sources.get(field) == UNAVAILABLE]
    if unavailable_required:
        return ValidationResult(False, "required_pit_field_unavailable", {"fields": sorted(unavailable_required)})
    current_only_required = [field for field in required_pit_fields if sources.get(field) == CURRENT_ONLY_METADATA]
    if current_only_required:
        return ValidationResult(False, "current_only_metadata_not_pit_complete", {"fields": sorted(current_only_required)})
    policy_required = [field for field in required_pit_fields if sources.get(field) == STATIC_CONSERVATIVE_POLICY_ASSUMPTION]
    if policy_required:
        return ValidationResult(False, "policy_assumption_not_historical_truth", {"fields": sorted(policy_required)})
    policy_not_allowed = [
        field
        for field, source in sources.items()
        if source == STATIC_CONSERVATIVE_POLICY_ASSUMPTION and field not in allowed_policy_fields
    ]
    if policy_not_allowed:
        return ValidationResult(False, "policy_assumption_not_preregistered_for_field", {"fields": sorted(policy_not_allowed)})
    future = {
        field: ts
        for field, ts in asof.items()
        if sources.get(field) in {PIT_HISTORICAL_MARKET_DATA, DERIVED_FROM_PIT_BARS}
        and int(ts) > int(candidate.decision_ts_ms)
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
    side: str | None = None,
) -> float:
    """Count crossed funding events.

    Compatibility: without side, returns the prior unsigned aggregate cost.
    With side, returns signed cashflow: long pays -N*r, short receives +N*r.
    """
    crossed = [r for r in records if int(entry_ts_ms) < int(r.funding_ts_ms) <= int(exit_ts_ms)]
    if side is None:
        return sum(abs(float(notional)) * float(r.funding_rate) for r in crossed)
    long_side = side.lower() in {"buy", "long"}
    sign = -1.0 if long_side else 1.0
    return sum(sign * abs(float(notional)) * float(r.funding_rate) for r in crossed)


def realized_funding_cashflow(
    *,
    notional: float,
    side: str,
    entry_ts_ms: int,
    exit_ts_ms: int,
    records: list[FundingRecord],
) -> float:
    """Signed funding cashflow using exchange funding economics."""
    return realized_funding_cost(
        notional=notional,
        side=side,
        entry_ts_ms=entry_ts_ms,
        exit_ts_ms=exit_ts_ms,
        records=records,
    )


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
        "source_class": STATIC_CONSERVATIVE_POLICY_ASSUMPTION if not historical_bid_ask_available else PIT_HISTORICAL_MARKET_DATA,
        "hierarchy": list(SPREAD_POLICY),
        "performance_dependent_selection": False,
    }


def slippage_policy_for_replay() -> dict[str, Any]:
    return {
        "source": SLIPPAGE_POLICY[0],
        "source_class": STATIC_CONSERVATIVE_POLICY_ASSUMPTION,
        "hierarchy": list(SLIPPAGE_POLICY),
        "performance_dependent_selection": False,
    }


def fee_policy_for_qualification() -> dict[str, Any]:
    return {
        "source": QUALIFICATION_FEE_SOURCE,
        "source_class": STATIC_CONSERVATIVE_POLICY_ASSUMPTION,
        "taker_fee_rate": TAKER_FEE_RATE_DEFAULT,
        "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
        "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        "cost_thresholds_changed": False,
    }
