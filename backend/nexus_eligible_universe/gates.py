"""Per-instrument gate evaluations for V18-C Eligible Universe.

Fail-closed: unknown / missing measured values never pass a gate that
would promote toward ELIGIBLE.
"""
from __future__ import annotations

from typing import Callable

from backend.nexus_eligible_universe.constants import (
    DELISTING_STATUSES,
    HALTED_STATUSES,
    MAX_ROUND_TRIP_COST_BPS,
    MAX_SPREAD_BPS,
    MIN_BOOK_DEPTH_USDT,
    MIN_DATA_COMPLETENESS,
    MIN_HISTORY_BARS,
    MIN_LISTING_AGE_DAYS,
    MIN_OI_VALUE_USDT,
    MIN_TRADE_COUNT_24H,
    MIN_TRUST_FOR_ELIGIBLE,
    MIN_TURNOVER_24H_USDT,
    TRADING_OK_STATUSES,
    TRUST_DEGRADED,
    TRUST_LICENSE_BLOCK,
    TRUST_UNAVAILABLE,
)
from backend.nexus_eligible_universe.models import GateResult, InstrumentSnapshot


def _ms_to_days(age_ms: float) -> float:
    return age_ms / 86_400_000.0


def gate_trading_status(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    status = inst.status
    if status is None or status == "" or str(status).upper() in {"UNKNOWN", "NONE"}:
        return GateResult("trading_status", False, False, "STATUS_UNKNOWN", status)
    if status in HALTED_STATUSES or status not in TRADING_OK_STATUSES:
        if status in HALTED_STATUSES or status in DELISTING_STATUSES:
            return GateResult("trading_status", False, True, f"STATUS_{status}", status)
        return GateResult("trading_status", False, True, f"NOT_TRADING:{status}", status)
    return GateResult("trading_status", True, True, "TRADING", status)


def gate_listing_age(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    if inst.launch_time_ms is None:
        return GateResult("listing_age", False, False, "LAUNCH_TIME_UNKNOWN", None)
    age_days = _ms_to_days(float(as_of_ms - int(inst.launch_time_ms)))
    if age_days < 0:
        return GateResult("listing_age", False, True, "LAUNCH_IN_FUTURE", age_days)
    if age_days < MIN_LISTING_AGE_DAYS:
        return GateResult("listing_age", False, True, "NEW_LISTING", age_days)
    return GateResult("listing_age", True, True, "AGE_OK", age_days)


def gate_turnover_24h(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    if inst.turnover_24h is None:
        return GateResult("turnover_24h", False, False, "TURNOVER_UNKNOWN", None)
    if float(inst.turnover_24h) < MIN_TURNOVER_24H_USDT:
        return GateResult(
            "turnover_24h", False, True, "TURNOVER_TOO_LOW", float(inst.turnover_24h)
        )
    return GateResult("turnover_24h", True, True, "TURNOVER_OK", float(inst.turnover_24h))


def gate_trade_frequency(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    if inst.trade_count_24h is None:
        return GateResult("trade_frequency", False, False, "TRADE_COUNT_UNKNOWN", None)
    if int(inst.trade_count_24h) < MIN_TRADE_COUNT_24H:
        return GateResult(
            "trade_frequency", False, True, "TRADE_FREQ_TOO_LOW", int(inst.trade_count_24h)
        )
    return GateResult(
        "trade_frequency", True, True, "TRADE_FREQ_OK", int(inst.trade_count_24h)
    )


def gate_spread(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    if inst.spread_bps is None:
        return GateResult("spread", False, False, "SPREAD_UNKNOWN", None)
    if float(inst.spread_bps) > MAX_SPREAD_BPS:
        return GateResult("spread", False, True, "WIDE_SPREAD", float(inst.spread_bps))
    if float(inst.spread_bps) < 0:
        return GateResult("spread", False, True, "SPREAD_INVALID", float(inst.spread_bps))
    return GateResult("spread", True, True, "SPREAD_OK", float(inst.spread_bps))


def gate_book_depth(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    if inst.book_depth_usdt is None:
        return GateResult("book_depth", False, False, "BOOK_DEPTH_UNKNOWN", None)
    if float(inst.book_depth_usdt) < MIN_BOOK_DEPTH_USDT:
        return GateResult(
            "book_depth", False, True, "BOOK_TOO_THIN", float(inst.book_depth_usdt)
        )
    return GateResult("book_depth", True, True, "BOOK_OK", float(inst.book_depth_usdt))


def gate_funding_availability(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    if inst.funding_available is None:
        return GateResult(
            "funding_availability", False, False, "FUNDING_AVAILABILITY_UNKNOWN", None
        )
    if not bool(inst.funding_available):
        return GateResult(
            "funding_availability", False, True, "FUNDING_UNAVAILABLE", False
        )
    return GateResult("funding_availability", True, True, "FUNDING_OK", True)


def gate_oi_availability(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    if inst.oi_available is None:
        return GateResult("oi_availability", False, False, "OI_AVAILABILITY_UNKNOWN", None)
    if not bool(inst.oi_available):
        return GateResult("oi_availability", False, True, "OI_UNAVAILABLE", False)
    if inst.open_interest_value is None:
        return GateResult("oi_availability", False, False, "OI_VALUE_UNKNOWN", None)
    if float(inst.open_interest_value) < MIN_OI_VALUE_USDT:
        return GateResult(
            "oi_availability", False, True, "OI_TOO_LOW", float(inst.open_interest_value)
        )
    return GateResult(
        "oi_availability", True, True, "OI_OK", float(inst.open_interest_value)
    )


def gate_data_completeness(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    if inst.data_completeness is None:
        return GateResult(
            "data_completeness", False, False, "COMPLETENESS_UNKNOWN", None
        )
    if float(inst.data_completeness) < MIN_DATA_COMPLETENESS:
        return GateResult(
            "data_completeness",
            False,
            True,
            "COMPLETENESS_LOW",
            float(inst.data_completeness),
        )
    return GateResult(
        "data_completeness", True, True, "COMPLETENESS_OK", float(inst.data_completeness)
    )


def gate_data_trust(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    trust = inst.data_trust_status
    if trust is None or trust == "" or str(trust).upper() == "UNKNOWN":
        return GateResult("data_trust", False, False, "TRUST_UNKNOWN", trust)
    if trust in TRUST_UNAVAILABLE:
        return GateResult("data_trust", False, True, "TRUST_UNAVAILABLE", trust)
    if trust in TRUST_LICENSE_BLOCK:
        return GateResult("data_trust", False, True, "TRUST_LICENSE_BLOCKED", trust)
    if trust in TRUST_DEGRADED:
        return GateResult("data_trust", False, True, "TRUST_DEGRADED", trust)
    if trust not in MIN_TRUST_FOR_ELIGIBLE:
        return GateResult("data_trust", False, True, f"TRUST_NOT_OK:{trust}", trust)
    return GateResult("data_trust", True, True, "TRUST_OK", trust)


def gate_contract_specs(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    missing: list[str] = []
    if not inst.symbol:
        missing.append("symbol")
    if inst.tick_size is None or float(inst.tick_size) <= 0:
        missing.append("tick_size")
    if inst.lot_size is None or float(inst.lot_size) <= 0:
        missing.append("lot_size")
    if inst.min_notional is None or float(inst.min_notional) <= 0:
        missing.append("min_notional")
    if inst.quote_coin is None:
        missing.append("quote_coin")
    if missing:
        known = all(
            getattr(inst, f, "SENTINEL") is not None
            for f in ("tick_size", "lot_size", "min_notional", "quote_coin")
        )
        # If any required field is None → unknown; if present but invalid → known fail
        any_unknown = any(
            getattr(inst, f) is None
            for f in ("tick_size", "lot_size", "min_notional", "quote_coin")
        ) or not inst.symbol
        return GateResult(
            "contract_specs",
            False,
            not any_unknown,
            "SPECS_INVALID:" + ",".join(missing),
            None,
        )
    if inst.quote_coin != "USDT":
        return GateResult(
            "contract_specs", False, True, f"QUOTE_UNSUPPORTED:{inst.quote_coin}", inst.quote_coin
        )
    return GateResult("contract_specs", True, True, "SPECS_OK", inst.tick_size)


def gate_delisting_state(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    if inst.delisting_flag is None and (
        inst.status is None or str(inst.status).upper() in {"UNKNOWN", "NONE", ""}
    ):
        return GateResult("delisting_state", False, False, "DELISTING_STATE_UNKNOWN", None)
    if inst.delisting_flag is True or (inst.status in DELISTING_STATUSES):
        return GateResult(
            "delisting_state",
            False,
            True,
            "DELISTING_RISK",
            inst.status or True,
        )
    if inst.delisting_flag is None:
        # Status known and not delisting → treat as known OK only if status is trading-ok
        if inst.status in TRADING_OK_STATUSES:
            return GateResult("delisting_state", True, True, "NOT_DELISTING", inst.status)
        return GateResult("delisting_state", False, False, "DELISTING_STATE_UNKNOWN", None)
    return GateResult("delisting_state", True, True, "NOT_DELISTING", False)


def gate_cost_feasibility(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    if inst.round_trip_cost_bps is None:
        return GateResult("cost_feasibility", False, False, "COST_UNKNOWN", None)
    if float(inst.round_trip_cost_bps) > MAX_ROUND_TRIP_COST_BPS:
        return GateResult(
            "cost_feasibility",
            False,
            True,
            "COST_INFEASIBLE",
            float(inst.round_trip_cost_bps),
        )
    if float(inst.round_trip_cost_bps) < 0:
        return GateResult(
            "cost_feasibility",
            False,
            True,
            "COST_INVALID",
            float(inst.round_trip_cost_bps),
        )
    return GateResult(
        "cost_feasibility", True, True, "COST_OK", float(inst.round_trip_cost_bps)
    )


def gate_history(inst: InstrumentSnapshot, *, as_of_ms: int) -> GateResult:
    """History depth gate (feeds INSUFFICIENT_HISTORY class)."""
    if inst.history_bars is None:
        return GateResult("history_bars", False, False, "HISTORY_UNKNOWN", None)
    if int(inst.history_bars) < MIN_HISTORY_BARS:
        return GateResult(
            "history_bars", False, True, "INSUFFICIENT_HISTORY", int(inst.history_bars)
        )
    return GateResult("history_bars", True, True, "HISTORY_OK", int(inst.history_bars))


GATE_RUNNERS: tuple[tuple[str, Callable[..., GateResult]], ...] = (
    ("trading_status", gate_trading_status),
    ("listing_age", gate_listing_age),
    ("turnover_24h", gate_turnover_24h),
    ("trade_frequency", gate_trade_frequency),
    ("spread", gate_spread),
    ("book_depth", gate_book_depth),
    ("funding_availability", gate_funding_availability),
    ("oi_availability", gate_oi_availability),
    ("data_completeness", gate_data_completeness),
    ("data_trust", gate_data_trust),
    ("contract_specs", gate_contract_specs),
    ("delisting_state", gate_delisting_state),
    ("cost_feasibility", gate_cost_feasibility),
)


def run_all_gates(inst: InstrumentSnapshot, *, as_of_ms: int) -> list[GateResult]:
    results = [fn(inst, as_of_ms=as_of_ms) for _, fn in GATE_RUNNERS]
    results.append(gate_history(inst, as_of_ms=as_of_ms))
    return results
