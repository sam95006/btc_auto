"""Attack tests — hard bans must block all survivorship leakage attempts."""
from __future__ import annotations

from backend.nexus_historical_universe.attacks import run_all_attacks
from backend.nexus_historical_universe.constants import ATTACK_IDS, HARD_BANS
from backend.nexus_historical_universe.evidence import evaluate_lane
from backend.nexus_historical_universe.guards import (
    guard_current_liquidity_substitution,
    guard_ignore_delistings,
    guard_pre_listing_data,
    guard_today_survivors_for_history,
)


def test_all_attacks_blocked_no_survivors():
    results = run_all_attacks()
    assert len(results) == len(ATTACK_IDS)
    assert all(r["attack_blocked"] for r in results)
    assert all(r["passed"] for r in results)
    assert all(not r["survivor"] for r in results)


def test_hard_ban_constants_cover_required():
    required = {
        "no_today_survivors_for_whole_history",
        "no_pre_listing_data",
        "no_ignoring_delistings",
        "no_current_liquidity_substitution",
        "no_exchange_write",
        "no_mainnet",
        "no_pr26_merge",
        "no_pr27_merge",
        "no_acceleration_report_edit",
    }
    assert required.issubset(set(HARD_BANS))


def test_guard_today_survivors_blocks_ghost_drop():
    g = guard_today_survivors_for_history(
        claimed_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"],
        pit_eligible_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "GHOSTUSDT"],
        today_survivors=["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "LATEUSDT"],
    )
    assert not g["ok"]
    assert g["status"] == "TODAY_SURVIVORS_FOR_HISTORY"
    assert "GHOSTUSDT" in g["dropped_historical"]


def test_guard_pre_listing_blocks():
    g = guard_pre_listing_data(
        symbol="LATEUSDT",
        listing_ms=1_735_689_600_000,
        as_of_ms=1_717_200_000_000,
        claimed_eligible=True,
        claimed_data_used=True,
    )
    assert not g["ok"]
    assert g["status"] == "PRE_LISTING_DATA"


def test_guard_ignore_delistings_blocks():
    g = guard_ignore_delistings(
        symbol="GHOSTUSDT",
        delisting_ms=1_725_000_000_000,
        as_of_ms=1_733_020_800_000,
        claimed_eligible=True,
    )
    assert not g["ok"]
    assert g["status"] == "IGNORE_DELISTINGS"


def test_guard_current_liquidity_blocks_future_obs():
    g = guard_current_liquidity_substitution(
        as_of_ms=1_717_200_000_000,
        liquidity_observation_ms=1_754_438_400_000,
        claimed_liquidity_score=0.95,
        historical_liquidity_score=0.01,
    )
    assert not g["ok"]
    assert g["status"] == "CURRENT_LIQUIDITY_SUBSTITUTION"


def test_evaluate_lane_pass_shape():
    # Uses worktree path by default; may be UNKNOWN head if path wrong — pass repo via cwd tests.
    from pathlib import Path

    evidence = evaluate_lane(repo_root=Path(__file__).resolve().parents[2])
    assert evidence["survivor_count"] == 0
    assert evidence["survivors"] == []
    assert evidence["attack_blocked_count"] == len(ATTACK_IDS)
    assert evidence["fixture_pass_count"] == 5
    assert evidence["passed"] is True
    assert evidence["exchange_write"] is False
    assert evidence["mainnet"] is False
    assert evidence["report_edited"] is False
