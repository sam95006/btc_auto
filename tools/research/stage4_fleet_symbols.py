"""Stage 4.13 fixed fleet symbol helpers (read-only, no auto universe)."""
from __future__ import annotations

import os
from typing import List, Tuple

STAGE4_FIXED_FLEET_SYMBOLS: Tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "PEPEUSDT",
)

# Bybit linear naming aliases (fetch under alias, keep configured symbol in logs).
SYMBOL_FETCH_ALIASES = {
    "PEPEUSDT": "1000PEPEUSDT",
}


def parse_symbol_list(raw: str) -> List[str]:
    return [s.strip().upper() for s in (raw or "").split(",") if s.strip()]


def resolve_stage4_symbols(*, cli_default: str = "ETHUSDT,BTCUSDT") -> List[str]:
    raw = os.environ.get("STAGE4_SYMBOLS", "").strip() or cli_default
    return parse_symbol_list(raw)


def fetch_symbol_for_market(symbol: str) -> str:
    """Return exchange symbol used for ticker/kline fetch."""
    sym = symbol.upper()
    return SYMBOL_FETCH_ALIASES.get(sym, sym)


def all_symbols_read_only(symbols: List[str]) -> bool:
    from tools.research.bybit_demo_client import STAGE4_READ_ONLY_SYMBOLS

    return all(s.upper() in STAGE4_READ_ONLY_SYMBOLS for s in symbols)
