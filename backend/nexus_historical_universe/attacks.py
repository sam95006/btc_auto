"""Attack scenarios — each must be blocked by guards (no survivors)."""
from __future__ import annotations

from typing import Any

from backend.nexus_historical_universe.constants import (
    ATTACK_IDS,
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    TODAY_SURVIVOR_ERA_MS,
)
from backend.nexus_historical_universe.fixtures import fixture_instruments, today_survivor_symbols
from backend.nexus_historical_universe.guards import (
    guard_current_liquidity_substitution,
    guard_ignore_delistings,
    guard_pre_listing_data,
    guard_today_survivors_for_history,
    honest_liquidity_score,
)
from backend.nexus_historical_universe.universe import reconstruct_universe


def _by_symbol(symbol: str) -> dict[str, Any]:
    for row in fixture_instruments():
        if row["symbol"] == symbol:
            return row
    raise KeyError(symbol)


def attack_today_survivors_for_history() -> dict[str, Any]:
    """Attack: rebuild mid-2024 universe from today's survivors only (drops GHOST)."""
    as_of = ERA_2024_06_01_MS
    honest = reconstruct_universe(as_of, retrieval_timestamp="FIXED")
    pit_eligible = list(honest["historical_eligible_universe"])
    survivors = today_survivor_symbols()
    # Attack claim: intersect survivors with anything that looks "alive today"
    claimed = sorted(set(pit_eligible) & set(survivors))
    attack = guard_today_survivors_for_history(
        claimed_symbols=claimed,
        pit_eligible_symbols=pit_eligible,
        today_survivors=survivors,
    )
    honest_guard = guard_today_survivors_for_history(
        claimed_symbols=pit_eligible,
        pit_eligible_symbols=pit_eligible,
        today_survivors=survivors,
    )
    blocked = attack["attack_blocked"] and not attack["ok"]
    ghost_in_pit = "GHOSTUSDT" in pit_eligible
    ghost_in_attack = "GHOSTUSDT" in claimed
    return {
        "attack_id": "today_survivors_for_history",
        "passed": blocked and ghost_in_pit and not ghost_in_attack and honest_guard["ok"],
        "attack_blocked": blocked,
        "survivor": not blocked,
        "severity": "CRITICAL",
        "detail": "today_survivors_reconstruction_blocked",
        "evidence": {
            "attack": attack,
            "honest": honest_guard,
            "ghost_in_pit": ghost_in_pit,
            "ghost_in_attack_claim": ghost_in_attack,
            "today_survivors": survivors,
            "pit_eligible": pit_eligible,
        },
    }


def attack_pre_listing_data() -> dict[str, Any]:
    """Attack: treat LATEUSDT as eligible / use its data before listing."""
    as_of = ERA_2024_06_01_MS
    late = _by_symbol("LATEUSDT")
    attack = guard_pre_listing_data(
        symbol="LATEUSDT",
        listing_ms=int(late["listing_ms"]),
        as_of_ms=as_of,
        claimed_eligible=True,
        claimed_data_used=True,
    )
    honest_uni = reconstruct_universe(as_of, retrieval_timestamp="FIXED")
    late_in_eligible = "LATEUSDT" in honest_uni["historical_eligible_universe"]
    late_not_yet = "LATEUSDT" in honest_uni["contracts_not_yet_listed"]
    honest = guard_pre_listing_data(
        symbol="LATEUSDT",
        listing_ms=int(late["listing_ms"]),
        as_of_ms=as_of,
        claimed_eligible=False,
        claimed_data_used=False,
    )
    blocked = attack["attack_blocked"] and not attack["ok"]
    return {
        "attack_id": "pre_listing_data",
        "passed": blocked and not late_in_eligible and late_not_yet and honest["ok"],
        "attack_blocked": blocked,
        "survivor": not blocked,
        "severity": "CRITICAL",
        "detail": "pre_listing_data_blocked",
        "evidence": {
            "attack": attack,
            "honest": honest,
            "late_in_eligible": late_in_eligible,
            "late_not_yet_listed": late_not_yet,
        },
    }


def attack_ignore_delistings() -> dict[str, Any]:
    """Attack: keep GHOSTUSDT eligible after delisting."""
    as_of = ERA_2024_12_01_MS  # after ghost_delist
    ghost = _by_symbol("GHOSTUSDT")
    attack = guard_ignore_delistings(
        symbol="GHOSTUSDT",
        delisting_ms=int(ghost["delisting_ms"]),
        as_of_ms=as_of,
        claimed_eligible=True,
    )
    before = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    after = reconstruct_universe(as_of, retrieval_timestamp="FIXED")
    ghost_before = "GHOSTUSDT" in before["historical_eligible_universe"]
    ghost_after = "GHOSTUSDT" in after["historical_eligible_universe"]
    ghost_delisted_bucket = "GHOSTUSDT" in after["contracts_delisted"]
    honest = guard_ignore_delistings(
        symbol="GHOSTUSDT",
        delisting_ms=int(ghost["delisting_ms"]),
        as_of_ms=as_of,
        claimed_eligible=False,
    )
    blocked = attack["attack_blocked"] and not attack["ok"]
    return {
        "attack_id": "ignore_delistings",
        "passed": blocked
        and ghost_before
        and not ghost_after
        and ghost_delisted_bucket
        and honest["ok"],
        "attack_blocked": blocked,
        "survivor": not blocked,
        "severity": "CRITICAL",
        "detail": "ignore_delistings_blocked",
        "evidence": {
            "attack": attack,
            "honest": honest,
            "ghost_before_eligible": ghost_before,
            "ghost_after_eligible": ghost_after,
            "ghost_in_delisted_bucket": ghost_delisted_bucket,
        },
    }


def attack_current_liquidity_substitution() -> dict[str, Any]:
    """Attack: use TODAY liquidity score for THINUSDT at mid-2024 as_of."""
    as_of = ERA_2024_06_01_MS
    thin = _by_symbol("THINUSDT")
    historical = honest_liquidity_score(thin, as_of_ms=as_of)
    # Pull today's observation (attack bait in fixtures)
    today_obs = None
    for obs in thin["liquidity_observations"]:
        if int(obs["observation_ms"]) == TODAY_SURVIVOR_ERA_MS:
            today_obs = obs
            break
    assert today_obs is not None
    attack = guard_current_liquidity_substitution(
        as_of_ms=as_of,
        liquidity_observation_ms=int(today_obs["observation_ms"]),
        claimed_liquidity_score=float(today_obs["liquidity_score"]),
        historical_liquidity_score=historical,
    )
    honest_uni = reconstruct_universe(as_of, retrieval_timestamp="FIXED")
    thin_detail = next(d for d in honest_uni["instrument_details"] if d["symbol"] == "THINUSDT")
    pit_score = (thin_detail.get("liquidity") or {}).get("liquidity_score")
    pit_obs_ms = thin_detail.get("liquidity_observation_ms")
    honest = guard_current_liquidity_substitution(
        as_of_ms=as_of,
        liquidity_observation_ms=pit_obs_ms,
        claimed_liquidity_score=pit_score,
        historical_liquidity_score=historical,
    )
    # Honest reconstruction must keep THIN excluded (low historical liquidity / incomplete)
    thin_excluded = "THINUSDT" in honest_uni["historical_excluded_universe"]
    blocked = attack["attack_blocked"] and not attack["ok"]
    return {
        "attack_id": "current_liquidity_substitution",
        "passed": blocked
        and thin_excluded
        and honest["ok"]
        and float(pit_score or 0) == float(historical or -1)
        and int(pit_obs_ms or 0) <= as_of,
        "attack_blocked": blocked,
        "survivor": not blocked,
        "severity": "CRITICAL",
        "detail": "current_liquidity_substitution_blocked",
        "evidence": {
            "attack": attack,
            "honest": honest,
            "historical_liquidity_score": historical,
            "today_liquidity_score": float(today_obs["liquidity_score"]),
            "pit_liquidity_score": pit_score,
            "thin_excluded": thin_excluded,
        },
    }


ATTACK_FNS = {
    "today_survivors_for_history": attack_today_survivors_for_history,
    "pre_listing_data": attack_pre_listing_data,
    "ignore_delistings": attack_ignore_delistings,
    "current_liquidity_substitution": attack_current_liquidity_substitution,
}


def run_all_attacks() -> list[dict[str, Any]]:
    return [ATTACK_FNS[aid]() for aid in ATTACK_IDS]
