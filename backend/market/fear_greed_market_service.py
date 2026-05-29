"""Crypto Fear & Greed Index (Alternative.me — no API key)."""

from __future__ import annotations

from typing import Any, Dict

from backend.market.external_market_http import ExternalMarketHttp, TimedCache
from config.external_market_config import (
    FEAR_GREED_BASE_URL,
    FEAR_GREED_ENABLED,
    FEAR_GREED_EXTREME_FEAR,
    FEAR_GREED_EXTREME_GREED,
    FEAR_GREED_REFRESH_SECONDS,
)


def _classify(value: int) -> str:
    if value <= FEAR_GREED_EXTREME_FEAR:
        return "extreme_fear"
    if value < 45:
        return "fear"
    if value <= 55:
        return "neutral"
    if value < FEAR_GREED_EXTREME_GREED:
        return "greed"
    return "extreme_greed"


class FearGreedMarketService:
    def __init__(self, http=None):
        self.http = http or ExternalMarketHttp()
        self._cache = TimedCache(FEAR_GREED_REFRESH_SECONDS)

    def configured(self) -> bool:
        return FEAR_GREED_ENABLED

    def fetch_index(self) -> Dict[str, Any]:
        cached = self._cache.get()
        if cached is not None:
            return cached

        result: Dict[str, Any] = {
            "source": "alternative_me_fear_greed",
            "configured": self.configured(),
            "ok": False,
            "value": 50,
            "classification": "neutral",
            "extreme_fear": False,
            "extreme_greed": False,
            "error": "",
        }
        if not FEAR_GREED_ENABLED:
            result["error"] = "fear_greed_disabled"
            self._cache.set(result)
            return result

        try:
            payload = self.http.get_json(f"{FEAR_GREED_BASE_URL}/fng/", params={"limit": 1, "format": "json"})
            rows = list((payload or {}).get("data") or [])
            row = rows[0] if rows else {}
            value = int(float(row.get("value") or 50))
            value = max(0, min(100, value))
            classification = _classify(value)
            result.update(
                {
                    "ok": True,
                    "value": value,
                    "classification": classification,
                    "extreme_fear": classification == "extreme_fear",
                    "extreme_greed": classification == "extreme_greed",
                    "timestamp": row.get("timestamp"),
                }
            )
        except Exception as exc:
            result["error"] = str(exc)

        self._cache.set(result)
        return result
