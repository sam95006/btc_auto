"""Historical Eligible / Excluded Universe reconstruction (survivorship-safe)."""
from __future__ import annotations

from typing import Any

from backend.nexus_historical_universe.constants import (
    DEFAULT_MIN_DATA_COMPLETENESS,
    DEFAULT_MIN_LIQUIDITY_SCORE,
    HARD_BANS,
    SCHEMA,
    SCHEMA_VERSION,
    TRADABLE_STATUSES,
)
from backend.nexus_historical_universe.events import (
    build_contract_spec_timeline,
    build_listing_delisting_events,
    events_as_of,
    specs_as_of,
)
from backend.nexus_historical_universe.fixtures import fixture_instruments
from backend.nexus_historical_universe.hashutil import sha_obj, universe_checksum, utc_now_iso
from backend.nexus_historical_universe.pit import (
    classify_listing_state,
    coin_exists_at,
    select_completeness_at,
    select_liquidity_at,
    select_spec_at,
    select_tradable_at,
)


class HistoricalUniverseError(ValueError):
    """Fail-closed historical universe errors."""


def _evaluate_instrument(
    row: dict[str, Any],
    *,
    as_of_ms: int,
    min_liquidity: float,
    min_completeness: float,
) -> dict[str, Any]:
    symbol = str(row["symbol"])
    listing_state = classify_listing_state(row, as_of_ms=as_of_ms)
    exists = coin_exists_at(row, as_of_ms=as_of_ms)
    spec = select_spec_at(row, as_of_ms=as_of_ms)
    liq = select_liquidity_at(row, as_of_ms=as_of_ms)
    tradable = select_tradable_at(row, as_of_ms=as_of_ms)
    completeness = select_completeness_at(row, as_of_ms=as_of_ms)

    reasons: list[str] = []
    if not exists:
        reasons.append("COIN_NOT_YET_EXISTING")
    if listing_state == "NOT_YET_LISTED":
        reasons.append("NOT_YET_LISTED")
    if listing_state == "DELISTED":
        reasons.append("DELISTED")
    if tradable is None:
        reasons.append("NO_TRADABLE_STATE_AS_OF")
    elif str(tradable.get("status")) not in TRADABLE_STATUSES:
        reasons.append(f"STATUS_{tradable.get('status')}")
    if spec is None:
        reasons.append("NO_CONTRACT_SPEC_AS_OF")
    if liq is None:
        reasons.append("NO_LIQUIDITY_OBSERVATION_AS_OF")
    else:
        if float(liq.get("liquidity_score") or 0.0) < float(min_liquidity):
            reasons.append("LIQUIDITY_BELOW_THRESHOLD")
    if completeness is None:
        reasons.append("NO_DATA_COMPLETENESS_AS_OF")
    else:
        if float(completeness.get("data_completeness") or 0.0) < float(min_completeness):
            reasons.append("DATA_INCOMPLETE")

    eligible = len(reasons) == 0 and listing_state == "LISTED"
    return {
        "symbol": symbol,
        "canonical_instrument_id": row.get("canonical_instrument_id"),
        "as_of_ms": int(as_of_ms),
        "coin_exists": exists,
        "listing_state": listing_state,
        "listed": listing_state == "LISTED",
        "not_yet_listed": listing_state == "NOT_YET_LISTED",
        "delisted": listing_state == "DELISTED",
        "listing_ms": row.get("listing_ms"),
        "delisting_ms": row.get("delisting_ms"),
        "tradable_state": (tradable or {}).get("status"),
        "tradable_effective_ms": (tradable or {}).get("effective_ms"),
        "contract_spec": spec,
        "liquidity": liq,
        "liquidity_observation_ms": (liq or {}).get("observation_ms"),
        "data_completeness": (completeness or {}).get("data_completeness"),
        "data_completeness_observation_ms": (completeness or {}).get("observation_ms"),
        "eligible": eligible,
        "exclusion_reasons": reasons,
    }


def reconstruct_universe(
    as_of_ms: int,
    *,
    instruments: list[dict[str, Any]] | None = None,
    min_liquidity_score: float = DEFAULT_MIN_LIQUIDITY_SCORE,
    min_data_completeness: float = DEFAULT_MIN_DATA_COMPLETENESS,
    retrieval_timestamp: str | None = None,
) -> dict[str, Any]:
    """Build Historical Eligible/Excluded Universe at as_of_ms.

    Per timestamp records: coins existing, contracts listed / not-yet-listed /
    delisted, PIT liquidity, tradable state, contract specs, data completeness.
    """
    as_of_ms = int(as_of_ms)
    rows = instruments if instruments is not None else fixture_instruments()
    retrieval_timestamp = retrieval_timestamp or utc_now_iso()

    details = [
        _evaluate_instrument(
            row,
            as_of_ms=as_of_ms,
            min_liquidity=min_liquidity_score,
            min_completeness=min_data_completeness,
        )
        for row in rows
    ]

    eligible = [d for d in details if d["eligible"]]
    excluded = [d for d in details if not d["eligible"]]
    coins_existing = sorted(d["symbol"] for d in details if d["coin_exists"])
    contracts_listed = sorted(d["symbol"] for d in details if d["listed"])
    not_yet_listed = sorted(d["symbol"] for d in details if d["not_yet_listed"])
    delisted = sorted(d["symbol"] for d in details if d["delisted"])
    eligible_symbols = sorted(d["symbol"] for d in eligible)
    excluded_symbols = sorted(d["symbol"] for d in excluded)

    listing_events = build_listing_delisting_events(rows)
    spec_timeline = build_contract_spec_timeline(rows)

    result = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "as_of_ms": as_of_ms,
        "retrieval_timestamp": retrieval_timestamp,
        "source_kind": "sanitized_fixture",
        "coins_existing": coins_existing,
        "contracts_listed": contracts_listed,
        "contracts_not_yet_listed": not_yet_listed,
        "contracts_delisted": delisted,
        "historical_eligible_universe": eligible_symbols,
        "historical_excluded_universe": excluded_symbols,
        "eligible_count": len(eligible_symbols),
        "excluded_count": len(excluded_symbols),
        "eligible_details": eligible,
        "excluded_details": excluded,
        "instrument_details": details,
        "listing_delisting_events_as_of": events_as_of(as_of_ms, rows),
        "listing_delisting_events_full": listing_events,
        "contract_spec_timeline_as_of": specs_as_of(as_of_ms, rows),
        "contract_spec_timeline_full": spec_timeline,
        "thresholds": {
            "min_liquidity_score": min_liquidity_score,
            "min_data_completeness": min_data_completeness,
        },
        "universe_checksum": universe_checksum(
            as_of_ms=as_of_ms,
            eligible_symbols=eligible_symbols,
            excluded_symbols=excluded_symbols,
        ),
        "hard_bans": list(HARD_BANS),
        "exchange_write": False,
        "mainnet": False,
        "real_money": False,
        "evidence_class": "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE",
    }
    result["result_checksum"] = sha_obj(
        {
            "as_of_ms": as_of_ms,
            "eligible": eligible_symbols,
            "excluded": excluded_symbols,
            "listed": contracts_listed,
            "delisted": delisted,
            "not_yet": not_yet_listed,
        }
    )
    return result
