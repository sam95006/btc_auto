"""CoinMarketCap: global metrics (BTC dominance) + sector momentum."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.market.external_market_http import ExternalMarketHttp, TimedCache
from config.external_market_config import (
    CMC_BTC_DOMINANCE_ALT_REDUCE,
    COINMARKETCAP_API_KEY,
    COINMARKETCAP_BASE_URL,
    CMC_REFRESH_SECONDS,
)


class CoinMarketCapMarketService:
    def __init__(self, http=None):
        self.http = http or ExternalMarketHttp()
        self._cache = TimedCache(CMC_REFRESH_SECONDS)

    def configured(self) -> bool:
        return bool(COINMARKETCAP_API_KEY)

    def fetch_global_metrics(self) -> Dict[str, Any]:
        cached = self._cache.get()
        if cached is not None:
            return cached

        result = {
            "source": "coinmarketcap",
            "configured": self.configured(),
            "ok": False,
            "btc_dominance": 0.0,
            "total_market_cap_usd": 0.0,
            "alt_leverage_reduce": False,
            "hot_sectors": [],
            "error": "",
        }
        if not self.configured():
            result["error"] = "coinmarketcap_api_key_missing"
            self._cache.set(result)
            return result

        headers = {"Accept": "application/json", "X-CMC_PRO_API_KEY": COINMARKETCAP_API_KEY}
        try:
            global_payload = self.http.get_json(
                f"{COINMARKETCAP_BASE_URL}/global-metrics/quotes/latest",
                headers=headers,
            )
            data = (global_payload.get("data") or {}) if isinstance(global_payload, dict) else {}
            quote = (data.get("quote") or {}).get("USD") or {}
            btc_dominance = float(quote.get("btc_dominance") or data.get("btc_dominance") or 0.0)
            total_cap = float(quote.get("total_market_cap") or 0.0)

            hot_sectors: List[Dict[str, Any]] = []
            try:
                categories = self.http.get_json(
                    f"{COINMARKETCAP_BASE_URL}/cryptocurrency/categories",
                    headers=headers,
                    params={"limit": 20},
                )
                rows = categories.get("data") if isinstance(categories, dict) else []
                ranked = []
                for row in rows or []:
                    if not isinstance(row, dict):
                        continue
                    change = float(
                        (row.get("market_cap_change") or row.get("volume_change") or row.get("avg_price_change") or 0.0)
                    )
                    ranked.append(
                        {
                            "name": str(row.get("name") or ""),
                            "market_cap_change_24h_pct": round(change, 4),
                            "volume_24h": round(float(row.get("volume") or 0.0), 2),
                        }
                    )
                hot_sectors = sorted(ranked, key=lambda item: item["market_cap_change_24h_pct"], reverse=True)[:5]
            except Exception:
                hot_sectors = []

            result.update(
                {
                    "ok": True,
                    "btc_dominance": round(btc_dominance, 4),
                    "total_market_cap_usd": round(total_cap, 2),
                    "alt_leverage_reduce": btc_dominance >= CMC_BTC_DOMINANCE_ALT_REDUCE,
                    "hot_sectors": hot_sectors,
                    "btc_dominance_threshold": CMC_BTC_DOMINANCE_ALT_REDUCE,
                }
            )
        except Exception as exc:
            result["error"] = str(exc)

        self._cache.set(result)
        return result
