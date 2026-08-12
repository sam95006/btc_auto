"""Listing / delisting survivorship attack expansions (beyond base V17-E quartet)."""
from __future__ import annotations

from typing import Any

from backend.nexus_historical_universe.attacks import run_all_attacks
from backend.nexus_historical_universe.constants import (
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    ERA_2025_03_01_MS,
)
from backend.nexus_historical_universe.fixtures import fixture_instruments
from backend.nexus_historical_universe.guards import (
    guard_ignore_delistings,
    guard_pre_listing_data,
    guard_today_survivors_for_history,
)
from backend.nexus_historical_universe.universe import reconstruct_universe


def _by_symbol(symbol: str) -> dict[str, Any]:
    for row in fixture_instruments():
        if row["symbol"] == symbol:
            return row
    raise KeyError(symbol)


def _attack(name: str, blocked: bool, detail: str, **extra: Any) -> dict[str, Any]:
    return {
        "attack_id": name,
        "blocked": blocked,
        "survivor": not blocked,
        "detail": detail,
        **extra,
    }


def attack_listing_minus_one_ms() -> dict[str, Any]:
    """Attack: claim LATEUSDT eligible at listing_ms - 1."""
    late = _by_symbol("LATEUSDT")
    listing = int(late["listing_ms"])
    as_of = listing - 1
    attack = guard_pre_listing_data(
        symbol="LATEUSDT",
        listing_ms=listing,
        as_of_ms=as_of,
        claimed_eligible=True,
        claimed_data_used=True,
    )
    uni = reconstruct_universe(as_of, retrieval_timestamp="FIXED")
    in_eligible = "LATEUSDT" in uni["historical_eligible_universe"]
    blocked = attack["attack_blocked"] and not attack["ok"] and not in_eligible
    return _attack(
        "listing_minus_one_ms",
        blocked,
        f"as_of={as_of} listing={listing}",
        evidence={"attack": attack, "in_eligible": in_eligible},
    )


def attack_listing_exact_ms_honest() -> dict[str, Any]:
    """Honest: at exact listing_ms, LATE may become listed (guard must not false-positive)."""
    late = _by_symbol("LATEUSDT")
    listing = int(late["listing_ms"])
    honest = guard_pre_listing_data(
        symbol="LATEUSDT",
        listing_ms=listing,
        as_of_ms=listing,
        claimed_eligible=True,
        claimed_data_used=True,
    )
    # At listing instant, claimed eligible is allowed by pre-listing guard.
    blocked = honest["ok"] and not honest["attack_blocked"]
    return _attack(
        "listing_exact_ms_honest",
        blocked,
        f"status={honest['status']}",
        evidence=honest,
    )


def attack_delisting_exact_ms() -> dict[str, Any]:
    """Attack: keep GHOST eligible at/after delisting_ms."""
    ghost = _by_symbol("GHOSTUSDT")
    delist = int(ghost["delisting_ms"])
    attack = guard_ignore_delistings(
        symbol="GHOSTUSDT",
        delisting_ms=delist,
        as_of_ms=delist,
        claimed_eligible=True,
    )
    # delisting_ms > as_of => still listed; at exact equality, still_listed is False
    # because guard uses delisting_ms > as_of_ms.
    blocked = attack["attack_blocked"] and not attack["ok"]
    uni = reconstruct_universe(delist, retrieval_timestamp="FIXED")
    ghost_eligible = "GHOSTUSDT" in uni["historical_eligible_universe"]
    return _attack(
        "delisting_exact_ms",
        blocked and not ghost_eligible,
        f"delist={delist} ghost_eligible={ghost_eligible}",
        evidence={"attack": attack, "ghost_eligible": ghost_eligible},
    )


def attack_delisting_plus_one_ms() -> dict[str, Any]:
    ghost = _by_symbol("GHOSTUSDT")
    delist = int(ghost["delisting_ms"])
    as_of = delist + 1
    attack = guard_ignore_delistings(
        symbol="GHOSTUSDT",
        delisting_ms=delist,
        as_of_ms=as_of,
        claimed_eligible=True,
    )
    blocked = attack["attack_blocked"] and not attack["ok"]
    return _attack("delisting_plus_one_ms", blocked, f"as_of={as_of}", evidence=attack)


def attack_relist_future_into_past_era() -> dict[str, Any]:
    """Attack: include LATEUSDT in June-2024 eligible set because it exists in Mar-2025."""
    past = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    future = reconstruct_universe(ERA_2025_03_01_MS, retrieval_timestamp="FIXED")
    future_syms = set(future["historical_eligible_universe"])
    past_syms = set(past["historical_eligible_universe"])
    claimed = sorted(past_syms | (future_syms - past_syms))  # inject future listings
    attack = guard_today_survivors_for_history(
        claimed_symbols=claimed,
        pit_eligible_symbols=sorted(past_syms),
        today_survivors=sorted(future_syms),
    )
    late_in_past = "LATEUSDT" in past_syms
    late_in_claim = "LATEUSDT" in claimed
    blocked = attack["attack_blocked"] and not attack["ok"] and not late_in_past and late_in_claim
    return _attack(
        "relist_future_into_past_era",
        blocked,
        f"late_in_past={late_in_past} late_in_claim={late_in_claim}",
        evidence={"attack": attack},
    )


def attack_ghost_persists_across_eras() -> dict[str, Any]:
    """Attack: keep delisted GHOST in Dec-2024 eligible via Jun membership bleed."""
    jun = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    dec = reconstruct_universe(ERA_2024_12_01_MS, retrieval_timestamp="FIXED")
    claimed = sorted(set(dec["historical_eligible_universe"]) | {"GHOSTUSDT"})
    attack = guard_ignore_delistings(
        symbol="GHOSTUSDT",
        delisting_ms=int(_by_symbol("GHOSTUSDT")["delisting_ms"]),
        as_of_ms=ERA_2024_12_01_MS,
        claimed_eligible=True,
    )
    ghost_jun = "GHOSTUSDT" in jun["historical_eligible_universe"]
    ghost_dec = "GHOSTUSDT" in dec["historical_eligible_universe"]
    blocked = (
        attack["attack_blocked"]
        and not attack["ok"]
        and ghost_jun
        and not ghost_dec
        and "GHOSTUSDT" in claimed
    )
    return _attack(
        "ghost_persists_across_eras",
        blocked,
        f"jun={ghost_jun} dec={ghost_dec}",
        evidence={"attack": attack, "claimed": claimed},
    )


def attack_base_v17e_quartet_still_clean() -> dict[str, Any]:
    """Sanity: base V17-E attacks remain 0 survivors (not a meaningless re-run claim — expansion gate)."""
    results = run_all_attacks()
    survivors = [r["attack_id"] for r in results if r.get("survivor") or not r.get("attack_blocked")]
    blocked = len(survivors) == 0
    return _attack(
        "base_v17e_quartet_still_clean",
        blocked,
        f"base_survivors={survivors}",
        base_attack_count=len(results),
        base_survivors=survivors,
    )


def run_listing_delisting_attacks() -> dict[str, Any]:
    attacks = [
        attack_listing_minus_one_ms(),
        attack_listing_exact_ms_honest(),
        attack_delisting_exact_ms(),
        attack_delisting_plus_one_ms(),
        attack_relist_future_into_past_era(),
        attack_ghost_persists_across_eras(),
        attack_base_v17e_quartet_still_clean(),
    ]
    survivors = [a["attack_id"] for a in attacks if a.get("survivor")]
    return {
        "schema": "v17_deep_listing_delisting_v1",
        "attack_count": len(attacks),
        "blocked_count": sum(1 for a in attacks if a.get("blocked")),
        "survivor_count": len(survivors),
        "survivors": survivors,
        "pass": len(survivors) == 0,
        "attacks": attacks,
    }
