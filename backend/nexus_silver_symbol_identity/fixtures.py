"""Control fixtures for silver symbol identity — not market performance."""
from __future__ import annotations

from typing import Any

from backend.nexus_silver_symbol_identity.constants import EVIDENCE_CLASS
from backend.nexus_silver_symbol_identity.depeg import make_depeg_period
from backend.nexus_silver_symbol_identity.normalize import normalize_raw_instrument
from backend.nexus_silver_symbol_identity.registry import SilverInstrumentRegistry


def raw_binance_perp_btcusdt() -> dict[str, Any]:
    return {
        "exchange": "binance",
        "exchange_symbol": "BTCUSDT",
        "market_type": "perp",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "margin_kind": "linear",
        "contract_multiplier": 1,
        "tick_size": 0.1,
        "lot_size": 0.001,
        "min_notional": 5.0,
        "listing_time": "2019-09-08T00:00:00Z",
        "delisting_time": None,
        "contract_rule_version": "v1",
    }


def raw_bybit_perp_btcusdt() -> dict[str, Any]:
    return {
        "exchange": "bybit",
        "exchange_symbol": "BTCUSDT",
        "market_type": "perp",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "margin_kind": "linear",
        "contract_multiplier": 1,
        "tick_size": 0.1,
        "lot_size": 0.001,
        "min_notional": 5.0,
        "listing_time": "2020-03-25T00:00:00Z",
        "delisting_time": None,
        "contract_rule_version": "v1",
    }


def raw_binance_spot_btcusdt() -> dict[str, Any]:
    return {
        "exchange": "binance",
        "exchange_symbol": "BTCUSDT",
        "market_type": "spot",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "margin_kind": "na",
        "contract_multiplier": 1,
        "tick_size": 0.01,
        "lot_size": 0.00001,
        "min_notional": 10.0,
        "listing_time": "2017-08-17T00:00:00Z",
        "delisting_time": None,
        "contract_rule_version": "v1",
    }


def raw_binance_perp_btcusdt_spec_v2() -> dict[str, Any]:
    raw = raw_binance_perp_btcusdt()
    raw["contract_rule_version"] = "v2"
    raw["tick_size"] = 0.5
    raw["min_notional"] = 5.0
    return raw


def raw_delisted_ghost() -> dict[str, Any]:
    return {
        "exchange": "bybit",
        "exchange_symbol": "GHOSTUSDT",
        "market_type": "perp",
        "base_asset": "GHOST",
        "quote_asset": "USDT",
        "margin_kind": "linear",
        "contract_multiplier": 1,
        "tick_size": 0.0001,
        "lot_size": 1,
        "min_notional": 5.0,
        "listing_time": "2023-01-01T00:00:00Z",
        "delisting_time": "2024-06-01T00:00:00Z",
        "contract_rule_version": "v1",
    }


def raw_pepe_pre_rename() -> dict[str, Any]:
    return {
        "exchange": "bybit",
        "exchange_symbol": "PEPEUSDT",
        "market_type": "perp",
        "base_asset": "PEPE",
        "quote_asset": "USDT",
        "margin_kind": "linear",
        "contract_multiplier": 1,
        "tick_size": 0.0000001,
        "lot_size": 100,
        "min_notional": 5.0,
        "listing_time": "2023-05-01T00:00:00Z",
        "delisting_time": None,
        "contract_rule_version": "v1",
    }


def raw_usdt_perp_with_depeg() -> dict[str, Any]:
    raw = raw_binance_perp_btcusdt()
    raw["depeg_periods"] = [
        make_depeg_period(
            asset="USDT",
            peg_asset="USD",
            start_time="2022-05-12T00:00:00Z",
            end_time="2022-05-13T12:00:00Z",
            max_deviation_bps=150.0,
            note="UST_contagion_fixture",
        )
    ]
    return raw


def build_fixture_registry() -> SilverInstrumentRegistry:
    reg = SilverInstrumentRegistry()
    for raw in (
        raw_binance_perp_btcusdt(),
        raw_bybit_perp_btcusdt(),
        raw_binance_spot_btcusdt(),
        raw_binance_perp_btcusdt_spec_v2(),
        raw_delisted_ghost(),
        raw_pepe_pre_rename(),
        raw_usdt_perp_with_depeg(),
    ):
        reg.upsert_raw(raw)
    return reg


def fixture_catalog() -> dict[str, Any]:
    return {
        "evidence_class": EVIDENCE_CLASS,
        "fixtures": [
            "cross_exchange_btcusdt_distinct",
            "spot_vs_perp_distinct",
            "contract_rule_version_distinct",
            "delisted_retained",
            "symbol_rename_lineage",
            "stablecoin_depeg_retained",
        ],
        "normalized_samples": [
            normalize_raw_instrument(raw_binance_perp_btcusdt())["canonical_instrument_id"],
            normalize_raw_instrument(raw_bybit_perp_btcusdt())["canonical_instrument_id"],
            normalize_raw_instrument(raw_binance_spot_btcusdt())["canonical_instrument_id"],
        ],
    }
