"""V18.2 Phase A — BLOCK root-cause census classifier.

Maps per-instrument gate failures + known wiring/schema gaps onto the
founder-required primary_block_reason vocabulary. Does NOT lower gates.
Does NOT invent eligibility. Missing stays missing.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from backend.nexus_eligible_universe.models import InstrumentSnapshot, UniverseDecision

# Founder-required primary_block_reason vocabulary (exact).
PRIMARY_BLOCK_REASONS: tuple[str, ...] = (
    "ADAPTER_DATA_MISSING",
    "ADAPTER_SCHEMA_ERROR",
    "NORMALIZATION_ERROR",
    "SYMBOL_IDENTITY_ERROR",
    "PIT_ERROR",
    "STALE_DATA",
    "LOW_DATA_TRUST",
    "INSUFFICIENT_HISTORY",
    "LOW_LIQUIDITY",
    "WIDE_SPREAD",
    "INSUFFICIENT_DEPTH",
    "FUNDING_UNAVAILABLE",
    "OI_UNAVAILABLE",
    "COST_UNKNOWN",
    "COST_INFEASIBLE",
    "NEW_LISTING",
    "DELISTING_RISK",
    "MARKET_INACTIVE",
    "GATE_CONFIGURATION_ERROR",
    "VALID_SAFETY_BLOCK",
    "UNKNOWN_REQUIRES_REVIEW",
)

# Engineering reasons first — these are false-blocks when data existed upstream.
_ENGINEERING_PRIORITY: tuple[str, ...] = (
    "SYMBOL_IDENTITY_ERROR",
    "ADAPTER_SCHEMA_ERROR",
    "ADAPTER_DATA_MISSING",
    "NORMALIZATION_ERROR",
    "PIT_ERROR",
    "GATE_CONFIGURATION_ERROR",
)

# Fields the Bybit instruments-info / tickers payloads are known to carry but
# V18.1 adapter/cycle path dropped or never wired (confirmed from fixtures + code).
_ADAPTER_SCHEMA_DROPPED_FIELDS: frozenset[str] = frozenset(
    {
        "tick_size",
        "lot_size",
        "min_notional",
        "funding_rate",
        "funding_available",
        "open_interest_value",
        "oi_available",
        "mark_price",
        "index_price",
    }
)

_CYCLE_ENRICHMENT_FIELDS: frozenset[str] = frozenset(
    {
        "turnover_24h",
        "spread_bps",
        "book_depth_usdt",
        "history_bars",
        "data_completeness",
        "data_trust_status",
        "round_trip_cost_bps",
    }
)

# Present on some venues (e.g. Binance 24hr count) but NOT on Bybit public linear ticker.
# Absence after live ticker enrichment is a known exchange gap → fail-closed safety, not schema drop.
_KNOWN_EXCHANGE_GAP_FIELDS: frozenset[str] = frozenset({"trade_count_24h"})


def _missing_fields(inst: InstrumentSnapshot) -> list[str]:
    checks: list[tuple[str, Any]] = [
        ("status", inst.status),
        ("quote_coin", inst.quote_coin),
        ("launch_time_ms", inst.launch_time_ms),
        ("tick_size", inst.tick_size),
        ("lot_size", inst.lot_size),
        ("min_notional", inst.min_notional),
        ("turnover_24h", inst.turnover_24h),
        ("trade_count_24h", inst.trade_count_24h),
        ("spread_bps", inst.spread_bps),
        ("book_depth_usdt", inst.book_depth_usdt),
        ("funding_available", inst.funding_available),
        ("oi_available", inst.oi_available),
        ("open_interest_value", inst.open_interest_value),
        ("history_bars", inst.history_bars),
        ("data_completeness", inst.data_completeness),
        ("data_trust_status", inst.data_trust_status),
        ("delisting_flag", inst.delisting_flag),
        ("round_trip_cost_bps", inst.round_trip_cost_bps),
        ("last_price", inst.last_price),
    ]
    return [name for name, val in checks if val is None or val == ""]


def _gate_fail_reasons(decision: UniverseDecision) -> list[str]:
    out: list[str] = []
    for g in decision.gates:
        if g.passed and g.known:
            continue
        if not g.known:
            out.append(f"{g.gate}:UNKNOWN:{g.detail}")
        else:
            out.append(f"{g.gate}:FAIL:{g.detail}")
    return out


def _map_gate_to_block_reason(gate: str, detail: str, known: bool) -> str:
    d = (detail or "").upper()
    g = gate.lower()

    if g == "trading_status":
        if not known:
            return "ADAPTER_DATA_MISSING"
        if "DELIST" in d or "SETTL" in d or "CLOSED" in d:
            return "DELISTING_RISK"
        return "MARKET_INACTIVE"

    if g == "delisting_state":
        if not known:
            return "ADAPTER_DATA_MISSING"
        return "DELISTING_RISK"

    if g == "contract_specs":
        # Specs live on instruments-info; None means adapter schema drop or norm miss.
        return "ADAPTER_SCHEMA_ERROR"

    if g == "listing_age":
        if not known:
            return "ADAPTER_DATA_MISSING"
        if "NEW_LISTING" in d:
            return "NEW_LISTING"
        return "VALID_SAFETY_BLOCK"

    if g == "turnover_24h":
        if not known:
            return "ADAPTER_DATA_MISSING"
        return "LOW_LIQUIDITY"

    if g == "trade_frequency":
        if not known:
            # Bybit public ticker does not publish 24h trade count — fail-closed safety.
            return "VALID_SAFETY_BLOCK"
        return "LOW_LIQUIDITY"

    if g == "spread":
        if not known:
            return "ADAPTER_DATA_MISSING"
        return "WIDE_SPREAD"

    if g == "book_depth":
        if not known:
            return "ADAPTER_DATA_MISSING"
        return "INSUFFICIENT_DEPTH"

    if g == "funding_availability":
        if not known:
            return "ADAPTER_SCHEMA_ERROR"  # on Bybit ticker, dropped by adapter
        return "FUNDING_UNAVAILABLE"

    if g == "oi_availability":
        if not known:
            return "ADAPTER_SCHEMA_ERROR"
        return "OI_UNAVAILABLE"

    if g == "data_completeness":
        if not known:
            return "GATE_CONFIGURATION_ERROR"
        return "LOW_DATA_TRUST"

    if g == "data_trust":
        if not known:
            return "GATE_CONFIGURATION_ERROR"
        if "STALE" in d:
            return "STALE_DATA"
        return "LOW_DATA_TRUST"

    if g == "cost_feasibility":
        if not known:
            return "COST_UNKNOWN"
        return "COST_INFEASIBLE"

    if g == "history_bars":
        if not known:
            return "ADAPTER_DATA_MISSING"
        return "INSUFFICIENT_HISTORY"

    return "UNKNOWN_REQUIRES_REVIEW"


def classify_block_reasons(
    inst: InstrumentSnapshot,
    decision: UniverseDecision,
    *,
    source_adapter: str,
    normalization_status: str,
    pit_status: str,
    data_class: str,
) -> dict[str, Any]:
    """Produce one census row for a blocked (or non-ELIGIBLE) contract."""
    missing = _missing_fields(inst)
    secondary: list[str] = []
    seen: set[str] = set()

    # Explicit identity faults.
    if not inst.symbol or not str(inst.symbol).endswith("USDT"):
        secondary.append("SYMBOL_IDENTITY_ERROR")
        seen.add("SYMBOL_IDENTITY_ERROR")

    # Schema drops confirmed when catalog-derived specs are absent.
    schema_hits = [f for f in missing if f in _ADAPTER_SCHEMA_DROPPED_FIELDS]
    if schema_hits:
        secondary.append("ADAPTER_SCHEMA_ERROR")
        seen.add("ADAPTER_SCHEMA_ERROR")

    # Cycle enrichment gaps (orderbook/ticker-all/trust/cost/history).
    enrich_hits = [f for f in missing if f in _CYCLE_ENRICHMENT_FIELDS]
    if enrich_hits:
        secondary.append("ADAPTER_DATA_MISSING")
        seen.add("ADAPTER_DATA_MISSING")

    gap_hits = [f for f in missing if f in _KNOWN_EXCHANGE_GAP_FIELDS]
    if gap_hits and "VALID_SAFETY_BLOCK" not in seen:
        secondary.append("VALID_SAFETY_BLOCK")
        seen.add("VALID_SAFETY_BLOCK")

    if normalization_status not in {"OK", "PASS", "NORMALIZED"}:
        secondary.append("NORMALIZATION_ERROR")
        seen.add("NORMALIZATION_ERROR")

    if pit_status not in {"OK", "PASS", "PIT_OK", "N/A"}:
        secondary.append("PIT_ERROR")
        seen.add("PIT_ERROR")

    for g in decision.gates:
        if g.passed and g.known:
            continue
        reason = _map_gate_to_block_reason(g.gate, g.detail, g.known)
        if reason not in seen:
            secondary.append(reason)
            seen.add(reason)

    if not secondary:
        secondary.append("UNKNOWN_REQUIRES_REVIEW")

    # Primary: first engineering reason if present, else first mapped reason.
    primary = secondary[0]
    for eng in _ENGINEERING_PRIORITY:
        if eng in seen:
            primary = eng
            break

    # If universe_class is a pure measured safety fail with full fields present,
    # prefer VALID_SAFETY_BLOCK / specific safety code over engineering.
    if not schema_hits and not enrich_hits and primary in _ENGINEERING_PRIORITY:
        # No engineering gaps — keep safety-specific if any.
        for cand in secondary:
            if cand not in _ENGINEERING_PRIORITY and cand != "UNKNOWN_REQUIRES_REVIEW":
                primary = cand
                break
        else:
            primary = "VALID_SAFETY_BLOCK"

    # Deduplicate secondary preserving order; exclude primary.
    secondary_out = [r for r in secondary if r != primary]
    # Stable unique
    uniq: list[str] = []
    for r in secondary_out:
        if r not in uniq:
            uniq.append(r)

    listing_age_days = None
    if inst.launch_time_ms is not None and decision.as_of_ms:
        listing_age_days = (float(decision.as_of_ms) - float(inst.launch_time_ms)) / 86_400_000.0

    return {
        "exchange": inst.exchange,
        "symbol": inst.symbol,
        "instrument_status": inst.status,
        "data_class": data_class,
        "data_trust": inst.data_trust_status,
        "listing_age": listing_age_days,
        "turnover": inst.turnover_24h,
        "spread": inst.spread_bps,
        "depth": inst.book_depth_usdt,
        "funding_available": inst.funding_available,
        "OI_available": inst.oi_available,
        "trade_available": inst.trade_count_24h is not None,
        "mark_available": inst.last_price is not None,
        "cost_available": inst.round_trip_cost_bps is not None,
        "history_available": inst.history_bars is not None,
        "primary_block_reason": primary,
        "secondary_block_reasons": uniq,
        "missing_fields": missing,
        "source_adapter": source_adapter,
        "normalization_status": normalization_status,
        "PIT_status": pit_status,
        "final_universe_status": decision.universe_class,
        "gate_fail_trace": _gate_fail_reasons(decision),
        "universe_reasons": list(decision.reasons),
        "schema_dropped_fields": schema_hits,
        "enrichment_missing_fields": enrich_hits,
    }


def aggregate_census(rows: list[dict[str, Any]]) -> dict[str, Any]:
    hist: Counter[str] = Counter()
    single = 0
    multi = 0
    for row in rows:
        primary = str(row.get("primary_block_reason") or "UNKNOWN_REQUIRES_REVIEW")
        hist[primary] += 1
        secs = list(row.get("secondary_block_reasons") or [])
        if len(secs) == 0:
            single += 1
        else:
            multi += 1

    def _count_primary(prefix_or_exact: str) -> int:
        return int(hist.get(prefix_or_exact, 0))

    adapter_fault = _count_primary("ADAPTER_DATA_MISSING") + _count_primary(
        "ADAPTER_SCHEMA_ERROR"
    )
    normalization_fault = _count_primary("NORMALIZATION_ERROR")
    gate_config_fault = _count_primary("GATE_CONFIGURATION_ERROR")
    valid_safety = _count_primary("VALID_SAFETY_BLOCK")
    # Also count pure safety primaries as valid safety for aggregate transparency.
    for k in (
        "LOW_LIQUIDITY",
        "WIDE_SPREAD",
        "INSUFFICIENT_DEPTH",
        "INSUFFICIENT_HISTORY",
        "NEW_LISTING",
        "DELISTING_RISK",
        "MARKET_INACTIVE",
        "FUNDING_UNAVAILABLE",
        "OI_UNAVAILABLE",
        "COST_INFEASIBLE",
        "LOW_DATA_TRUST",
        "STALE_DATA",
    ):
        # These are measured safety when primary — counted separately in histogram;
        # valid_safety_block_count stays the explicit VALID_SAFETY_BLOCK bucket plus
        # only when primary is the explicit token (founder aggregate field).
        _ = k
    unknown = _count_primary("UNKNOWN_REQUIRES_REVIEW")

    return {
        "contract_count": len(rows),
        "block_reason_histogram": dict(sorted(hist.items(), key=lambda kv: (-kv[1], kv[0]))),
        "contracts_with_single_reason": single,
        "contracts_with_multiple_reasons": multi,
        "adapter_fault_count": adapter_fault,
        "normalization_fault_count": normalization_fault,
        "gate_config_fault_count": gate_config_fault,
        "valid_safety_block_count": valid_safety,
        "unknown_count": unknown,
    }
