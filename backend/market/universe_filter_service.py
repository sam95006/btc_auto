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

    def resolve_pure_ai_universe(
        self,
        *,
        futures_client=None,
        radar_scan: dict | None = None,
        max_symbols: int = 20,
        include_core_first: bool = True,
    ) -> list[str]:
        """
        Pure AI universe:
        - Always prefer core fleets (BTC/ETH/SOL/PEPE).
        - Fill remaining slots with RADAR scan candidates (if available),
          then liquidity-ranked tickers, then static TOP_LIQUIDITY_SYMBOLS.
        """
        max_symbols = max(4, int(max_symbols or 20))
        radar_scan = dict(radar_scan or {})

        def _is_tradable(sym: str) -> bool:
            if not futures_client:
                return True
            fn = getattr(futures_client, "is_tradable_symbol", None)
            if callable(fn):
                try:
                    return bool(fn(sym))
                except Exception:
                    return True
            return True

        merged: list[str] = []
        seen = set()

        if include_core_first:
            for sym in sorted(CORE_FLEET_SYMBOLS):
                sym = normalize_symbol(sym)
                if sym and sym not in seen and _is_tradable(sym):
                    seen.add(sym)
                    merged.append(sym)

        # 1) RADAR scan candidates (ranked already by candidate_score)
        for row in list(radar_scan.get("candidates") or [])[: max_symbols * 2]:
            sym = normalize_symbol((row or {}).get("symbol"))
            if not sym or sym in seen:
                continue
            if include_core_first and sym in CORE_FLEET_SYMBOLS:
                continue
            if not sym.endswith("USDT"):
                continue
            if _is_tradable(sym):
                seen.add(sym)
                merged.append(sym)
            if len(merged) >= max_symbols:
                return merged[:max_symbols]

        # 2) Liquidity-ranked tickers (24h quoteVolume)
        dynamic: list[str] = []
        if futures_client and getattr(futures_client, "is_configured", lambda: False)():
            try:
                tickers = futures_client.fetch_24h_tickers() or []
                ranked: list[tuple[float, str]] = []
                for item in tickers:
                    sym = normalize_symbol((item or {}).get("symbol"))
                    if not sym.endswith("USDT"):
                        continue
                    if include_core_first and sym in CORE_FLEET_SYMBOLS:
                        continue
                    quote_volume = float((item or {}).get("quoteVolume") or (item or {}).get("quote_volume") or 0.0)
                    if quote_volume < float(self.min_notional or RADAR_UNIVERSE_MIN_NOTIONAL):
                        continue
                    ranked.append((quote_volume, sym))
                ranked.sort(reverse=True)
                dynamic = [sym for _v, sym in ranked[: max_symbols * 4]]
            except Exception:
                dynamic = []

        # 3) Static liquidity list as last fallback (excluding cores)
        static = [
            sym
            for sym in (normalize_symbol(item) for item in TOP_LIQUIDITY_SYMBOLS)
            if sym and (not include_core_first or sym not in CORE_FLEET_SYMBOLS)
        ]

        for sym in dynamic + static:
            if not sym or sym in seen:
                continue
            if not sym.endswith("USDT"):
                continue
            if _is_tradable(sym):
                seen.add(sym)
                merged.append(sym)
            if len(merged) >= max_symbols:
                break

        return merged[:max_symbols]
