"""Fleet vs symbol routing: core fleets own BTC/ETH/SOL/PEPE; all other symbols via RADAR."""

from __future__ import annotations

import os

CORE_FLEETS = frozenset({"BTC", "ETH", "SOL", "PEPE"})

CORE_FLEET_SYMBOLS = frozenset(
    {
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "1000PEPEUSDT",
        "PEPEUSDT",
    }
)

_DEFAULT_SYMBOL_BY_FLEET = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "PEPE": "1000PEPEUSDT",
}

_SYMBOL_TO_CORE_FLEET = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
    "1000PEPEUSDT": "PEPE",
    "PEPEUSDT": "PEPE",
}


def normalize_symbol(symbol) -> str:
    return str(symbol or "").upper().replace("/", "").strip()


def resolve_core_fleet_symbol(fleet: str) -> str:
    fleet = str(fleet or "").upper()
    env_key = f"BINANCE_FUTURES_TESTNET_SYMBOL_{fleet}"
    return normalize_symbol(os.getenv(env_key, _DEFAULT_SYMBOL_BY_FLEET.get(fleet, f"{fleet}USDT")))


def is_core_fleet(fleet: str) -> bool:
    return str(fleet or "").upper() in CORE_FLEETS


def is_core_symbol(symbol: str) -> bool:
    return normalize_symbol(symbol) in CORE_FLEET_SYMBOLS


def is_radar_only_symbol(symbol: str) -> bool:
    symbol = normalize_symbol(symbol)
    return bool(symbol) and not is_core_symbol(symbol)


def core_fleet_for_symbol(symbol: str) -> str | None:
    return _SYMBOL_TO_CORE_FLEET.get(normalize_symbol(symbol))


def fleet_for_exchange_position(symbol: str, core_symbol_map: dict | None = None) -> str:
    symbol = normalize_symbol(symbol)
    core_symbol_map = core_symbol_map or {}
    if symbol in core_symbol_map:
        return str(core_symbol_map[symbol]).upper()
    return core_fleet_for_symbol(symbol) or "RADAR"


def validate_futures_open_route(fleet: str, symbol: str) -> tuple[bool, str]:
    """
    BTC/ETH/SOL/PEPE 艦隊只能開各自合約；
    其餘幣種只能由 RADAR 雷達站開倉。
    """
    fleet = str(fleet or "").upper()
    symbol = normalize_symbol(symbol)
    if not symbol:
        return False, "missing_symbol"

    if is_core_symbol(symbol):
        owner = core_fleet_for_symbol(symbol)
        if fleet == "RADAR":
            return False, "radar_cannot_open_core_symbol"
        if not is_core_fleet(fleet):
            return False, "core_symbol_requires_core_fleet"
        if owner and fleet != owner:
            return False, f"core_symbol_owned_by_{owner}"
        return True, "core_fleet_route"

    if is_core_fleet(fleet):
        return False, "alt_symbol_must_use_radar"
    if fleet != "RADAR":
        return False, "alt_symbol_must_use_radar"
    return True, "radar_route"
