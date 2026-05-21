from __future__ import annotations

from config.fleet_routing_config import CORE_FLEET_SYMBOLS, normalize_symbol
from config.universe_config import (
    RADAR_UNIVERSE_MAX_SYMBOLS,
    RADAR_UNIVERSE_MIN_NOTIONAL,
    TOP_LIQUIDITY_SYMBOLS,
)


class UniverseFilterService:
    """Resolve RADAR scan universe (Top-N liquidity, P1)."""

    def __init__(self, max_symbols=None, min_notional=None):
        self.max_symbols = int(max_symbols or RADAR_UNIVERSE_MAX_SYMBOLS)
        self.min_notional = float(min_notional or RADAR_UNIVERSE_MIN_NOTIONAL)

    def resolve_scan_symbols(self, futures_client=None):
        static = [
            symbol
            for symbol in (normalize_symbol(item) for item in TOP_LIQUIDITY_SYMBOLS)
            if symbol not in CORE_FLEET_SYMBOLS
        ][: self.max_symbols]
        if not futures_client or not getattr(futures_client, "is_configured", lambda: False)():
            return static

        try:
            tickers = futures_client.fetch_24h_tickers() or []
        except Exception:
            return static

        ranked = []
        for item in tickers:
            symbol = normalize_symbol(item.get("symbol"))
            if not symbol.endswith("USDT") or symbol in CORE_FLEET_SYMBOLS:
                continue
            quote_volume = float(item.get("quoteVolume") or item.get("quote_volume") or 0.0)
            if quote_volume < self.min_notional:
                continue
            ranked.append((quote_volume, symbol))

        if not ranked:
            return static

        ranked.sort(reverse=True)
        dynamic = [symbol for _volume, symbol in ranked[: self.max_symbols]]
        merged = []
        seen = set()
        for symbol in dynamic + static:
            if symbol in seen:
                continue
            seen.add(symbol)
            merged.append(symbol)
            if len(merged) >= self.max_symbols:
                break
        return merged
