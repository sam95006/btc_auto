"""Sanitized historical instrument fixtures for survivorship control.

Era-bound observations only. No live exchange, no mainnet, no real money.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_historical_universe.constants import (
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    ERA_2025_03_01_MS,
    TODAY_SURVIVOR_ERA_MS,
)
from backend.nexus_historical_universe.hashutil import sha_obj


def _spec(
    *,
    effective_ms: int,
    tick_size: float,
    qty_step: float,
    min_notional: float,
    min_qty: float = 0.001,
    contract_type: str = "LinearPerpetual",
    quote: str = "USDT",
    settle: str = "USDT",
    contract_rule_version: str = "v1",
) -> dict[str, Any]:
    return {
        "effective_ms": int(effective_ms),
        "contract_type": contract_type,
        "quote_coin": quote,
        "settle_coin": settle,
        "tick_size": tick_size,
        "qty_step": qty_step,
        "minimum_notional": min_notional,
        "minimum_order_qty": min_qty,
        "contract_rule_version": contract_rule_version,
    }


def _liq(*, observation_ms: int, score: float, turnover: float, depth: float) -> dict[str, Any]:
    return {
        "observation_ms": int(observation_ms),
        "liquidity_score": float(score),
        "turnover_usdt": float(turnover),
        "depth_usdt": float(depth),
    }


def _tradable(*, effective_ms: int, status: str) -> dict[str, Any]:
    return {"effective_ms": int(effective_ms), "status": status}


def _complete(*, observation_ms: int, completeness: float) -> dict[str, Any]:
    return {"observation_ms": int(observation_ms), "data_completeness": float(completeness)}


def _instrument(
    *,
    symbol: str,
    base: str,
    listing_ms: int,
    delisting_ms: int | None,
    specs: list[dict[str, Any]],
    liquidity: list[dict[str, Any]],
    tradable: list[dict[str, Any]],
    completeness: list[dict[str, Any]],
    coin_exists_from_ms: int | None = None,
) -> dict[str, Any]:
    body = {
        "symbol": symbol,
        "canonical_instrument_id": f"bybit:linear:{symbol}",
        "base_coin": base,
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "listing_ms": int(listing_ms),
        "delisting_ms": int(delisting_ms) if delisting_ms is not None else None,
        "coin_exists_from_ms": int(coin_exists_from_ms if coin_exists_from_ms is not None else listing_ms),
        "spec_timeline": sorted(specs, key=lambda s: int(s["effective_ms"])),
        "liquidity_observations": sorted(liquidity, key=lambda s: int(s["observation_ms"])),
        "tradable_states": sorted(tradable, key=lambda s: int(s["effective_ms"])),
        "data_completeness_observations": sorted(
            completeness, key=lambda s: int(s["observation_ms"])
        ),
        "source_kind": "sanitized_fixture",
        "trading_write": False,
        "mainnet_trading": False,
        "real_money": False,
    }
    body["instrument_checksum"] = sha_obj(
        {
            "symbol": symbol,
            "listing_ms": body["listing_ms"],
            "delisting_ms": body["delisting_ms"],
            "specs": body["spec_timeline"],
            "liquidity": body["liquidity_observations"],
            "tradable": body["tradable_states"],
            "completeness": body["data_completeness_observations"],
        }
    )
    return body


def fixture_instruments() -> list[dict[str, Any]]:
    """Multi-era instrument set with listing/delisting, spec drift, liquidity eras."""
    btc_list = 1_577_836_800_000  # 2020-01-01
    eth_list = 1_577_836_800_000
    sol_list = 1_640_995_200_000  # 2022-01-01
    pepe_list = 1_704_067_200_000  # 2024-01-01
    late_list = 1_735_689_600_000  # 2025-01-01
    ghost_list = 1_609_459_200_000  # 2021-01-01
    ghost_delist = 1_725_000_000_000  # ~2024-08-29
    # Spec change for BTC mid-2024
    btc_spec_v2_ms = 1_720_000_000_000

    return [
        _instrument(
            symbol="BTCUSDT",
            base="BTC",
            listing_ms=btc_list,
            delisting_ms=None,
            specs=[
                _spec(effective_ms=btc_list, tick_size=0.1, qty_step=0.001, min_notional=5.0, contract_rule_version="v1"),
                _spec(effective_ms=btc_spec_v2_ms, tick_size=0.5, qty_step=0.001, min_notional=5.0, contract_rule_version="v2"),
            ],
            liquidity=[
                _liq(observation_ms=ERA_2024_06_01_MS, score=0.99, turnover=1e9, depth=5e7),
                _liq(observation_ms=ERA_2024_12_01_MS, score=0.995, turnover=1.2e9, depth=6e7),
                _liq(observation_ms=ERA_2025_03_01_MS, score=0.997, turnover=1.4e9, depth=7e7),
                _liq(observation_ms=TODAY_SURVIVOR_ERA_MS, score=0.999, turnover=2e9, depth=1e8),
            ],
            tradable=[
                _tradable(effective_ms=btc_list, status="Trading"),
            ],
            completeness=[
                _complete(observation_ms=ERA_2024_06_01_MS, completeness=1.0),
                _complete(observation_ms=ERA_2024_12_01_MS, completeness=1.0),
                _complete(observation_ms=ERA_2025_03_01_MS, completeness=1.0),
                _complete(observation_ms=TODAY_SURVIVOR_ERA_MS, completeness=1.0),
            ],
        ),
        _instrument(
            symbol="ETHUSDT",
            base="ETH",
            listing_ms=eth_list,
            delisting_ms=None,
            specs=[
                _spec(effective_ms=eth_list, tick_size=0.01, qty_step=0.01, min_notional=5.0),
            ],
            liquidity=[
                _liq(observation_ms=ERA_2024_06_01_MS, score=0.95, turnover=5e8, depth=2e7),
                _liq(observation_ms=ERA_2024_12_01_MS, score=0.96, turnover=6e8, depth=2.5e7),
                _liq(observation_ms=ERA_2025_03_01_MS, score=0.97, turnover=7e8, depth=3e7),
                _liq(observation_ms=TODAY_SURVIVOR_ERA_MS, score=0.98, turnover=8e8, depth=3.5e7),
            ],
            tradable=[_tradable(effective_ms=eth_list, status="Trading")],
            completeness=[
                _complete(observation_ms=ERA_2024_06_01_MS, completeness=1.0),
                _complete(observation_ms=ERA_2024_12_01_MS, completeness=1.0),
                _complete(observation_ms=ERA_2025_03_01_MS, completeness=1.0),
                _complete(observation_ms=TODAY_SURVIVOR_ERA_MS, completeness=1.0),
            ],
        ),
        _instrument(
            symbol="SOLUSDT",
            base="SOL",
            listing_ms=sol_list,
            delisting_ms=None,
            specs=[
                _spec(effective_ms=sol_list, tick_size=0.001, qty_step=0.1, min_notional=5.0),
            ],
            liquidity=[
                _liq(observation_ms=ERA_2024_06_01_MS, score=0.80, turnover=8e7, depth=4e6),
                _liq(observation_ms=ERA_2024_12_01_MS, score=0.85, turnover=1e8, depth=5e6),
                _liq(observation_ms=ERA_2025_03_01_MS, score=0.88, turnover=1.2e8, depth=6e6),
                _liq(observation_ms=TODAY_SURVIVOR_ERA_MS, score=0.90, turnover=1.5e8, depth=7e6),
            ],
            tradable=[_tradable(effective_ms=sol_list, status="Trading")],
            completeness=[
                _complete(observation_ms=ERA_2024_06_01_MS, completeness=0.95),
                _complete(observation_ms=ERA_2024_12_01_MS, completeness=0.98),
                _complete(observation_ms=ERA_2025_03_01_MS, completeness=0.99),
                _complete(observation_ms=TODAY_SURVIVOR_ERA_MS, completeness=1.0),
            ],
        ),
        _instrument(
            symbol="PEPEUSDT",
            base="PEPE",
            listing_ms=pepe_list,
            delisting_ms=None,
            specs=[
                _spec(effective_ms=pepe_list, tick_size=1e-8, qty_step=100.0, min_notional=5.0, contract_rule_version="v1"),
                _spec(
                    effective_ms=ERA_2024_12_01_MS,
                    tick_size=1e-7,
                    qty_step=100.0,
                    min_notional=50.0,
                    contract_rule_version="v2_min_notional_bump",
                ),
            ],
            liquidity=[
                _liq(observation_ms=ERA_2024_06_01_MS, score=0.40, turnover=2e6, depth=1e5),
                _liq(observation_ms=ERA_2024_12_01_MS, score=0.55, turnover=5e6, depth=2e5),
                _liq(observation_ms=ERA_2025_03_01_MS, score=0.60, turnover=6e6, depth=2.5e5),
                _liq(observation_ms=TODAY_SURVIVOR_ERA_MS, score=0.70, turnover=1e7, depth=4e5),
            ],
            tradable=[_tradable(effective_ms=pepe_list, status="Trading")],
            completeness=[
                _complete(observation_ms=ERA_2024_06_01_MS, completeness=0.70),
                _complete(observation_ms=ERA_2024_12_01_MS, completeness=0.85),
                _complete(observation_ms=ERA_2025_03_01_MS, completeness=0.90),
                _complete(observation_ms=TODAY_SURVIVOR_ERA_MS, completeness=0.95),
            ],
        ),
        # Listed only in 2025 — must NOT appear in 2024 eligible sets.
        _instrument(
            symbol="LATEUSDT",
            base="LATE",
            listing_ms=late_list,
            delisting_ms=None,
            specs=[
                _spec(effective_ms=late_list, tick_size=0.001, qty_step=1.0, min_notional=5.0),
            ],
            liquidity=[
                # Attack bait: "current" high liquidity that must never leak into 2024.
                _liq(observation_ms=ERA_2025_03_01_MS, score=0.92, turnover=9e7, depth=3e6),
                _liq(observation_ms=TODAY_SURVIVOR_ERA_MS, score=0.99, turnover=2e8, depth=1e7),
            ],
            tradable=[_tradable(effective_ms=late_list, status="Trading")],
            completeness=[
                _complete(observation_ms=ERA_2025_03_01_MS, completeness=0.90),
                _complete(observation_ms=TODAY_SURVIVOR_ERA_MS, completeness=1.0),
            ],
            coin_exists_from_ms=late_list,
        ),
        # Historically listed then delisted — must appear in mid-2024, vanish after delist.
        _instrument(
            symbol="GHOSTUSDT",
            base="GHOST",
            listing_ms=ghost_list,
            delisting_ms=ghost_delist,
            specs=[
                _spec(effective_ms=ghost_list, tick_size=0.0001, qty_step=1.0, min_notional=5.0),
            ],
            liquidity=[
                _liq(observation_ms=ERA_2024_06_01_MS, score=0.35, turnover=1e6, depth=5e4),
                # No post-delist liquidity observation (honest). Attack may invent today score.
            ],
            tradable=[
                _tradable(effective_ms=ghost_list, status="Trading"),
                _tradable(effective_ms=ghost_delist, status="Delisted"),
            ],
            completeness=[
                _complete(observation_ms=ERA_2024_06_01_MS, completeness=0.80),
            ],
        ),
        # Illiquid / incomplete — stays excluded when gates apply.
        _instrument(
            symbol="THINUSDT",
            base="THIN",
            listing_ms=1_650_000_000_000,
            delisting_ms=None,
            specs=[
                _spec(effective_ms=1_650_000_000_000, tick_size=0.001, qty_step=1.0, min_notional=5.0),
            ],
            liquidity=[
                _liq(observation_ms=ERA_2024_06_01_MS, score=0.01, turnover=100.0, depth=10.0),
                _liq(observation_ms=ERA_2024_12_01_MS, score=0.02, turnover=200.0, depth=20.0),
                _liq(observation_ms=TODAY_SURVIVOR_ERA_MS, score=0.95, turnover=5e7, depth=2e6),  # attack bait
            ],
            tradable=[_tradable(effective_ms=1_650_000_000_000, status="Trading")],
            completeness=[
                _complete(observation_ms=ERA_2024_06_01_MS, completeness=0.20),
                _complete(observation_ms=ERA_2024_12_01_MS, completeness=0.30),
                _complete(observation_ms=TODAY_SURVIVOR_ERA_MS, completeness=1.0),
            ],
        ),
    ]


def today_survivor_symbols() -> list[str]:
    """Symbols still listed at TODAY_SURVIVOR_ERA — GHOST is gone; LATE is present."""
    as_of = TODAY_SURVIVOR_ERA_MS
    out: list[str] = []
    for row in fixture_instruments():
        listing = int(row["listing_ms"])
        delisting = row.get("delisting_ms")
        if listing > as_of:
            continue
        if delisting is not None and int(delisting) <= as_of:
            continue
        out.append(str(row["symbol"]))
    return sorted(out)


def fixture_catalog() -> dict[str, Any]:
    instruments = fixture_instruments()
    return {
        "schema": "v17_e_historical_universe_fixture_catalog_v1",
        "source_kind": "sanitized_fixture",
        "trading_write": False,
        "mainnet_trading": False,
        "real_money": False,
        "instrument_count": len(instruments),
        "eras_ms": {
            "ERA_2024_06_01_MS": ERA_2024_06_01_MS,
            "ERA_2024_12_01_MS": ERA_2024_12_01_MS,
            "ERA_2025_03_01_MS": ERA_2025_03_01_MS,
            "TODAY_SURVIVOR_ERA_MS": TODAY_SURVIVOR_ERA_MS,
        },
        "today_survivor_symbols": today_survivor_symbols(),
        "instruments": instruments,
        "catalog_checksum": sha_obj(
            {
                "symbols": sorted(i["symbol"] for i in instruments),
                "checksums": [i["instrument_checksum"] for i in sorted(instruments, key=lambda x: x["symbol"])],
            }
        ),
    }
