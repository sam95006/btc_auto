"""CoinGecko: top market-cap universe + per-coin liquidity."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.market.external_market_http import ExternalMarketHttp, ExternalMarketHttpError, TimedCache
from config.external_market_config import (
    COINGECKO_API_KEY,
    COINGECKO_BASE_URL,
    COINGECKO_MIN_VOLUME_USD,
    COINGECKO_REFRESH_SECONDS,
    COINGECKO_TOP_N,
)


from backend.market.binance_futures_symbol_map import coingecko_row_to_binance_symbol


class CoinGeckoMarketService:
    def __init__(self, http=None):
        self.http = http or ExternalMarketHttp()
        self._cache = TimedCache(COINGECKO_REFRESH_SECONDS)

    def configured(self) -> bool:
        return bool(COINGECKO_API_KEY)

    def fetch_top_markets(self) -> Dict[str, Any]:
        cached = self._cache.get()
        if cached is not None:
            return cached

        result = {
            "source": "coingecko",
            "configured": self.configured(),
            "ok": False,
            "symbols": [],
            "by_symbol": {},
            "error": "",
        }
        if not self.configured():
            result["error"] = "coingecko_api_key_missing"
            self._cache.set(result)
            return result

        headers = {"Accept": "application/json", "x-cg-demo-api-key": COINGECKO_API_KEY}
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": int(COINGECKO_TOP_N),
            "page": 1,
            "sparkline": "false",
        }
        try:
            rows = self.http.get_json(f"{COINGECKO_BASE_URL}/coins/markets", headers=headers, params=params)
            if not isinstance(rows, list):
                raise ExternalMarketHttpError("unexpected coingecko response")
            by_symbol: Dict[str, Dict[str, Any]] = {}
            symbols: List[str] = []
            for row in rows:
                symbol = coingecko_row_to_binance_symbol(row)
                if not symbol or not symbol.endswith("USDT"):
                    continue
                volume = float(row.get("total_volume") or 0.0)
                market_cap = float(row.get("market_cap") or 0.0)
                rank = int(row.get("market_cap_rank") or 0)
                by_symbol[symbol] = {
                    "symbol": symbol,
                    "rank": rank,
                    "volume_24h_usd": round(volume, 2),
                    "market_cap_usd": round(market_cap, 2),
                    "liquidity_ok": volume >= COINGECKO_MIN_VOLUME_USD,
                    "price_change_24h_pct": round(float(row.get("price_change_percentage_24h") or 0.0), 4),
                }
                symbols.append(symbol)
            result.update(
                {
                    "ok": True,
                    "symbols": symbols,
                    "by_symbol": by_symbol,
                    "top_n": COINGECKO_TOP_N,
                    "min_volume_usd": COINGECKO_MIN_VOLUME_USD,
                }
            )
        except Exception as exc:
            result["error"] = str(exc)

        self._cache.set(result)
        return result
