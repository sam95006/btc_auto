"""Hard-ban guards for survivorship / listing / liquidity leakage."""
from __future__ import annotations

from typing import Any

from backend.nexus_historical_universe.fixtures import today_survivor_symbols
from backend.nexus_historical_universe.pit import classify_listing_state, select_liquidity_at


def guard_today_survivors_for_history(
    *,
    claimed_symbols: list[str],
    pit_eligible_symbols: list[str],
    today_survivors: list[str] | None = None,
) -> dict[str, Any]:
    """HARD BAN: do not use today's survivors as the whole-history universe."""
    claimed = set(claimed_symbols)
    pit = set(pit_eligible_symbols)
    survivors = set(today_survivors if today_survivors is not None else today_survivor_symbols())
    dropped_historical = sorted(pit - claimed)
    # Attack shape: claimed equals survivors∩pit (or survivors) while pit has more (e.g. GHOST).
    only_survivors = claimed.issubset(survivors) and len(dropped_historical) > 0
    survivor_intersection = claimed == (pit & survivors) and claimed != pit
    banned = only_survivors or survivor_intersection or (claimed == survivors and claimed != pit)
    return {
        "ok": not banned and claimed == pit,
        "status": "TODAY_SURVIVORS_FOR_HISTORY" if banned or claimed != pit else "PASS",
        "attack_blocked": banned or claimed != pit,
        "dropped_historical": dropped_historical,
        "claimed": sorted(claimed),
        "pit_eligible": sorted(pit),
        "today_survivors": sorted(survivors),
    }


def guard_pre_listing_data(
    *,
    symbol: str,
    listing_ms: int | None,
    as_of_ms: int,
    claimed_eligible: bool,
    claimed_data_used: bool,
) -> dict[str, Any]:
    """HARD BAN: no pre-listing membership or data use."""
    listed = listing_ms is not None and int(listing_ms) <= int(as_of_ms)
    leak = (bool(claimed_eligible) or bool(claimed_data_used)) and not listed
    return {
        "ok": not leak,
        "status": "PRE_LISTING_DATA" if leak else "PASS",
        "attack_blocked": leak,
        "symbol": symbol,
        "listing_ms": listing_ms,
        "as_of_ms": int(as_of_ms),
        "claimed_eligible": claimed_eligible,
        "claimed_data_used": claimed_data_used,
    }


def guard_ignore_delistings(
    *,
    symbol: str,
    delisting_ms: int | None,
    as_of_ms: int,
    claimed_eligible: bool,
) -> dict[str, Any]:
    """HARD BAN: ignoring delistings (treating delisted contracts as eligible)."""
    still_listed = delisting_ms is None or int(delisting_ms) > int(as_of_ms)
    leak = bool(claimed_eligible) and not still_listed
    return {
        "ok": not leak,
        "status": "IGNORE_DELISTINGS" if leak else "PASS",
        "attack_blocked": leak,
        "symbol": symbol,
        "delisting_ms": delisting_ms,
        "as_of_ms": int(as_of_ms),
        "claimed_eligible": claimed_eligible,
    }


def guard_current_liquidity_substitution(
    *,
    as_of_ms: int,
    liquidity_observation_ms: int | None,
    claimed_liquidity_score: float | None,
    historical_liquidity_score: float | None,
) -> dict[str, Any]:
    """HARD BAN: substituting current/future liquidity for historical as_of."""
    future_obs = liquidity_observation_ms is not None and int(liquidity_observation_ms) > int(as_of_ms)
    substituted = False
    if (
        claimed_liquidity_score is not None
        and historical_liquidity_score is not None
        and float(claimed_liquidity_score) != float(historical_liquidity_score)
        and future_obs
    ):
        substituted = True
    if future_obs and claimed_liquidity_score is not None:
        substituted = True
    banned = future_obs or substituted
    return {
        "ok": not banned,
        "status": "CURRENT_LIQUIDITY_SUBSTITUTION" if banned else "PASS",
        "attack_blocked": banned,
        "as_of_ms": int(as_of_ms),
        "liquidity_observation_ms": liquidity_observation_ms,
        "claimed_liquidity_score": claimed_liquidity_score,
        "historical_liquidity_score": historical_liquidity_score,
        "future_observation": future_obs,
    }


def honest_membership_from_instrument(row: dict[str, Any], *, as_of_ms: int) -> bool:
    return classify_listing_state(row, as_of_ms=as_of_ms) == "LISTED"


def honest_liquidity_score(row: dict[str, Any], *, as_of_ms: int) -> float | None:
    liq = select_liquidity_at(row, as_of_ms=as_of_ms)
    if liq is None:
        return None
    return float(liq["liquidity_score"])
