"""Cross-exchange symbol collision attack tests."""
from __future__ import annotations

import os

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_deep_pit_survivorship.symbol_collision_attacks import (  # noqa: E402
    attack_collapse_cross_exchange_btcusdt,
    attack_collapse_spot_perp,
    attack_cross_venue_liquidity_substitution_by_symbol,
    attack_missing_exchange_component,
    attack_symbol_only_registry_merge,
    run_symbol_collision_attacks,
)


def test_symbol_collision_campaign_zero_survivors():
    report = run_symbol_collision_attacks()
    assert report["pass"] is True
    assert report["survivor_count"] == 0
    assert report["attack_count"] >= 6


def test_cross_exchange_btcusdt_not_collapsed():
    result = attack_collapse_cross_exchange_btcusdt()
    assert result["blocked"] is True
    assert result["binance_id"] != result["bybit_id"]


def test_symbol_only_registry_keeps_both_venues():
    result = attack_symbol_only_registry_merge()
    assert result["blocked"] is True
    assert result["honest_count"] >= 2


def test_spot_perp_not_collapsed():
    result = attack_collapse_spot_perp()
    assert result["blocked"] is True
    assert result["spot_id"] != result["perp_id"]


def test_missing_exchange_rejected():
    result = attack_missing_exchange_component()
    assert result["blocked"] is True


def test_cross_venue_liquidity_by_symbol_refused():
    result = attack_cross_venue_liquidity_substitution_by_symbol()
    assert result["blocked"] is True
