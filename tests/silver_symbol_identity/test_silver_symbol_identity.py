"""V17-C Silver Symbol Identity — fixture-only proofs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_silver_symbol_identity.constants import (  # noqa: E402
    CANONICAL_IDENTITY_FIELDS,
    EVIDENCE_CLASS,
    HARD_BANS,
    OWNED_PATHS,
)
from backend.nexus_silver_symbol_identity.depeg import (  # noqa: E402
    assert_depeg_periods_retained,
    attach_depeg_period,
    make_depeg_period,
    retained_depeg_periods,
)
from backend.nexus_silver_symbol_identity.fixtures import (  # noqa: E402
    build_fixture_registry,
    fixture_catalog,
    raw_binance_perp_btcusdt,
    raw_binance_perp_btcusdt_spec_v2,
    raw_binance_spot_btcusdt,
    raw_bybit_perp_btcusdt,
    raw_delisted_ghost,
    raw_pepe_pre_rename,
    raw_usdt_perp_with_depeg,
)
from backend.nexus_silver_symbol_identity.hard_bans import (  # noqa: E402
    HardBanViolation,
    assert_hard_bans_declared,
    refuse_exchange_write,
    refuse_mainnet,
    refuse_pr_integration,
)
from backend.nexus_silver_symbol_identity.identity import (  # noqa: E402
    build_canonical_asset_id,
    instruments_are_same_instrument,
    instruments_share_symbol_string,
)
from backend.nexus_silver_symbol_identity.lineage import detect_silent_rename  # noqa: E402
from backend.nexus_silver_symbol_identity.normalize import normalize_raw_instrument  # noqa: E402
from backend.nexus_silver_symbol_identity.registry import SilverInstrumentRegistry  # noqa: E402
from backend.nexus_silver_symbol_identity.schema import (  # noqa: E402
    build_schema,
    validate_silver_instrument,
)

ROOT = Path(__file__).resolve().parents[2]


def test_owned_paths_and_hard_bans():
    assert any("nexus_silver_symbol_identity" in p for p in OWNED_PATHS)
    declared = assert_hard_bans_declared()
    assert declared["ok"]
    assert "no_erase_delisted_instruments" in HARD_BANS
    assert "no_collapse_cross_exchange_symbols" in HARD_BANS
    assert "no_collapse_spot_perp_identity" in HARD_BANS
    assert "no_drop_stablecoin_depeg_periods" in HARD_BANS
    assert fixture_catalog()["evidence_class"] == EVIDENCE_CLASS


def test_canonical_identity_fields_present():
    required = {
        "canonical_asset_id",
        "canonical_instrument_id",
        "exchange_symbol",
        "quote_asset",
        "contract_multiplier",
        "tick_size",
        "lot_size",
        "min_notional",
        "listing_time",
        "delisting_time",
        "contract_rule_version",
    }
    assert required.issubset(set(CANONICAL_IDENTITY_FIELDS))
    # market type + margin kind cover spot/perp/future/options and inverse/linear
    assert "market_type" in CANONICAL_IDENTITY_FIELDS
    assert "margin_kind" in CANONICAL_IDENTITY_FIELDS
    record = normalize_raw_instrument(raw_binance_perp_btcusdt())
    for field in CANONICAL_IDENTITY_FIELDS:
        assert field in record
    assert validate_silver_instrument(record)["ok"]
    schema = build_schema()
    assert set(schema["required"]) == set(CANONICAL_IDENTITY_FIELDS)


def test_same_btcusdt_not_same_instrument_across_exchanges():
    binance = normalize_raw_instrument(raw_binance_perp_btcusdt())
    bybit = normalize_raw_instrument(raw_bybit_perp_btcusdt())
    assert instruments_share_symbol_string(binance, bybit)
    assert binance["exchange_symbol"] == bybit["exchange_symbol"] == "BTCUSDT"
    assert binance["canonical_asset_id"] == bybit["canonical_asset_id"] == "asset:btc"
    assert not instruments_are_same_instrument(binance, bybit)
    assert binance["canonical_instrument_id"] != bybit["canonical_instrument_id"]


def test_spot_not_equal_perp():
    spot = normalize_raw_instrument(raw_binance_spot_btcusdt())
    perp = normalize_raw_instrument(raw_binance_perp_btcusdt())
    assert spot["exchange"] == perp["exchange"]
    assert spot["exchange_symbol"] == perp["exchange_symbol"]
    assert spot["market_type"] == "spot"
    assert perp["market_type"] == "perp"
    assert spot["margin_kind"] == "na"
    assert perp["margin_kind"] == "linear"
    assert spot["canonical_instrument_id"] != perp["canonical_instrument_id"]


def test_contract_spec_versions_distinct():
    v1 = normalize_raw_instrument(raw_binance_perp_btcusdt())
    v2 = normalize_raw_instrument(raw_binance_perp_btcusdt_spec_v2())
    assert v1["contract_rule_version"] == "v1"
    assert v2["contract_rule_version"] == "v2"
    assert v1["tick_size"] != v2["tick_size"]
    assert v1["canonical_instrument_id"] != v2["canonical_instrument_id"]
    # Same asset, different instrument versions coexist.
    assert v1["canonical_asset_id"] == v2["canonical_asset_id"]


def test_delisted_not_erased():
    reg = SilverInstrumentRegistry()
    ghost = reg.upsert_raw(raw_delisted_ghost())
    assert ghost["status"] == "delisted"
    assert ghost["delisting_time"] is not None
    iid = ghost["canonical_instrument_id"]
    assert reg.get(iid) is not None
    # Explicit erase attempt is forbidden while record exists.
    ban = reg.erase_forbidden(iid)
    assert ban["ok"] is False
    assert ban["status"] == "ERASE_FORBIDDEN"
    # Active-only listing does not drop historical presence from full list.
    all_rows = reg.list_all(include_delisted=True)
    active_only = reg.list_all(include_delisted=False)
    assert any(r["canonical_instrument_id"] == iid for r in all_rows)
    assert all(r["canonical_instrument_id"] != iid for r in active_only)
    # Remains after subsequent upserts of other symbols.
    reg.upsert_raw(raw_binance_perp_btcusdt())
    assert reg.get(iid) is not None
    assert reg.get(iid)["delisting_time"] == ghost["delisting_time"]


def test_symbol_rename_lineage():
    reg = SilverInstrumentRegistry()
    pepe = reg.upsert_raw(raw_pepe_pre_rename())
    old_id = pepe["canonical_instrument_id"]
    payload = reg.rename(
        old_instrument_id=old_id,
        new_symbol="1000PEPEUSDT",
        effective_time="2023-11-01T00:00:00Z",
    )
    assert payload["erased_old"] is False
    assert payload["rename_lineage_id"]
    old = reg.get(old_id)
    new = reg.get(payload["new"]["canonical_instrument_id"])
    assert old is not None and new is not None
    assert old["status"] == "renamed"
    assert old["successor_instrument_id"] == new["canonical_instrument_id"]
    assert new["predecessor_instrument_id"] == old_id
    assert old["rename_lineage_id"] == new["rename_lineage_id"]
    silent = detect_silent_rename(
        previous_symbol="PEPEUSDT",
        observed_symbol="1000PEPEUSDT",
        rename_lineage_id=None,
    )
    assert silent["ok"] is False
    linked = detect_silent_rename(
        previous_symbol="PEPEUSDT",
        observed_symbol="1000PEPEUSDT",
        rename_lineage_id=payload["rename_lineage_id"],
    )
    assert linked["ok"] is True


def test_stablecoin_depeg_periods_retained():
    reg = SilverInstrumentRegistry()
    first = reg.upsert_raw(raw_usdt_perp_with_depeg())
    assert len(retained_depeg_periods(first, asset="USDT")) == 1
    # Second upsert without depeg payload must retain prior periods.
    raw2 = raw_binance_perp_btcusdt()
    raw2["depeg_periods"] = []
    second = reg.upsert_raw(raw2)
    check = assert_depeg_periods_retained(first, second)
    assert check["ok"]
    assert len(retained_depeg_periods(second, asset="USDT")) == 1
    # Additional period accumulates.
    period2 = make_depeg_period(
        asset="USDT",
        peg_asset="USD",
        start_time="2023-03-11T00:00:00Z",
        end_time="2023-03-12T00:00:00Z",
        max_deviation_bps=80.0,
        note="svb_fixture",
    )
    third = reg.upsert(attach_depeg_period(second, period2))
    assert len(retained_depeg_periods(third, asset="USDT")) == 2


def test_future_and_options_and_inverse_identities():
    future = normalize_raw_instrument(
        {
            "exchange": "binance",
            "exchange_symbol": "BTCUSDT_240329",
            "market_type": "future",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "margin_kind": "linear",
            "contract_multiplier": 1,
            "tick_size": 0.1,
            "lot_size": 0.001,
            "min_notional": 5,
            "listing_time": "2023-12-01T00:00:00Z",
            "contract_rule_version": "v1",
        }
    )
    inverse = normalize_raw_instrument(
        {
            "exchange": "binance",
            "exchange_symbol": "BTCUSD_PERP",
            "market_type": "perp",
            "base_asset": "BTC",
            "quote_asset": "USD",
            "margin_kind": "inverse",
            "contract_multiplier": 100,
            "tick_size": 0.1,
            "lot_size": 1,
            "min_notional": 0,
            "listing_time": "2020-01-01T00:00:00Z",
            "contract_rule_version": "v1",
        }
    )
    options = normalize_raw_instrument(
        {
            "exchange": "deribit",
            "exchange_symbol": "BTC-31DEC25-100000-C",
            "market_type": "options",
            "base_asset": "BTC",
            "quote_asset": "USD",
            "margin_kind": "inverse",
            "contract_multiplier": 1,
            "tick_size": 0.0005,
            "lot_size": 0.1,
            "min_notional": 0,
            "listing_time": "2025-01-01T00:00:00Z",
            "contract_rule_version": "v1",
        }
    )
    ids = {
        future["canonical_instrument_id"],
        inverse["canonical_instrument_id"],
        options["canonical_instrument_id"],
        normalize_raw_instrument(raw_binance_perp_btcusdt())["canonical_instrument_id"],
    }
    assert len(ids) == 4
    assert inverse["margin_kind"] == "inverse"
    assert build_canonical_asset_id("BTC") == "asset:btc"


def test_fixture_registry_smoke():
    reg = build_fixture_registry()
    rows = reg.list_all(include_delisted=True)
    assert len(rows) >= 5
    # Cross-exchange BTCUSDT both present and distinct.
    binance_perp = [
        r
        for r in rows
        if r["exchange"] == "binance"
        and r["exchange_symbol"] == "BTCUSDT"
        and r["market_type"] == "perp"
        and r["contract_rule_version"] == "v1"
    ]
    bybit_perp = [
        r
        for r in rows
        if r["exchange"] == "bybit" and r["exchange_symbol"] == "BTCUSDT" and r["market_type"] == "perp"
    ]
    assert len(binance_perp) == 1 and len(bybit_perp) == 1
    assert binance_perp[0]["canonical_instrument_id"] != bybit_perp[0]["canonical_instrument_id"]


def test_hard_ban_refusals():
    with pytest.raises(HardBanViolation):
        refuse_exchange_write(exchange_write=True)
    with pytest.raises(HardBanViolation):
        refuse_mainnet(mainnet=True)
    with pytest.raises(HardBanViolation):
        refuse_pr_integration(pr26=True)
    with pytest.raises(HardBanViolation):
        refuse_pr_integration(pr27=True)
    refuse_exchange_write(exchange_write=False)
    refuse_mainnet(mainnet=False)
    refuse_pr_integration(pr26=False, pr27=False)
