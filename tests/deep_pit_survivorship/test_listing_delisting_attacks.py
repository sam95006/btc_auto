"""Listing / delisting survivorship expansion tests."""
from __future__ import annotations

import os

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_deep_pit_survivorship.listing_delisting_attacks import (  # noqa: E402
    attack_delisting_exact_ms,
    attack_delisting_plus_one_ms,
    attack_ghost_persists_across_eras,
    attack_listing_exact_ms_honest,
    attack_listing_minus_one_ms,
    attack_relist_future_into_past_era,
    run_listing_delisting_attacks,
)


def test_listing_delisting_campaign_zero_survivors():
    report = run_listing_delisting_attacks()
    assert report["pass"] is True
    assert report["survivor_count"] == 0
    assert report["attack_count"] >= 7


def test_listing_minus_one_ms_blocked():
    result = attack_listing_minus_one_ms()
    assert result["blocked"] is True
    assert result["survivor"] is False


def test_listing_exact_ms_honest_allowed():
    result = attack_listing_exact_ms_honest()
    assert result["blocked"] is True  # "blocked" means attack/false-positive did not succeed


def test_delisting_exact_and_plus_one_blocked():
    assert attack_delisting_exact_ms()["blocked"] is True
    assert attack_delisting_plus_one_ms()["blocked"] is True


def test_future_listing_not_injected_into_past():
    result = attack_relist_future_into_past_era()
    assert result["blocked"] is True


def test_ghost_does_not_persist_after_delist():
    result = attack_ghost_persists_across_eras()
    assert result["blocked"] is True
