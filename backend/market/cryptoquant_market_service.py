"""CryptoQuant: exchange inflow whale alert + futures OI stress (advisory)."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.market.external_market_http import ExternalMarketHttp, TimedCache
from config.external_market_config import (
    CRYPTOQUANT_API_KEY,
    CRYPTOQUANT_BASE_URL,
    CRYPTOQUANT_INFLOW_SPIKE_BTC,
    CRYPTOQUANT_OI_STRESS_SCORE,
    CRYPTOQUANT_REFRESH_SECONDS,
)


def _extract_series_rows(payload: Any) -> List[dict]:
    if isinstance(payload, dict):
        result = payload.get("result") or payload.get("data")
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, list):
                return data
        if isinstance(result, list):
            return result
    if isinstance(payload, list):
        return payload
    return []


def _latest_value(rows: List[dict], keys: tuple[str, ...]) -> float:
    if not rows:
        return 0.0
    row = rows[-1] if isinstance(rows[-1], dict) else {}
    for key in keys:
        if key in row:
            return float(row.get(key) or 0.0)
    return 0.0


class CryptoQuantMarketService:
    def __init__(self, http=None):
        self.http = http or ExternalMarketHttp()
        self._cache = TimedCache(CRYPTOQUANT_REFRESH_SECONDS)

    def configured(self) -> bool:
        return bool(CRYPTOQUANT_API_KEY)

    def fetch_risk_signals(self) -> Dict[str, Any]:
        cached = self._cache.get()
        if cached is not None:
            return cached

        result = {
            "source": "cryptoquant",
            "configured": self.configured(),
            "ok": False,
            "btc_exchange_inflow": 0.0,
            "whale_dump_alert": False,
            "oi_stress": False,
            "reduce_spot_aggression": False,
            "error": "",
        }
        if not self.configured():
            result["error"] = "cryptoquant_api_key_missing"
            self._cache.set(result)
            return result

        headers = {"Accept": "application/json", "Authorization": f"Bearer {CRYPTOQUANT_API_KEY}"}
        inflow_btc = 0.0
        oi_stress = False
        errors: List[str] = []

        inflow_paths = (
            "/btc/exchange-flows/inflow",
            "/btc/exchange-flows/inflow-total",
        )
        for path in inflow_paths:
            try:
                payload = self.http.get_json(
                    f"{CRYPTOQUANT_BASE_URL}{path}",
                    headers=headers,
                    params={"exchange": "all_exchange", "window": "hour", "limit": 3},
                )
                rows = _extract_series_rows(payload)
                inflow_btc = _latest_value(rows, ("inflow_total", "value", "inflow"))
                if inflow_btc > 0:
                    break
            except Exception as exc:
                errors.append(f"{path}:{exc}")

        oi_paths = (
            "/btc/market-data/open-interest",
            "/btc/market-indicator/estimated-leverage-ratio",
        )
        leverage_ratio = 0.0
        for path in oi_paths:
            try:
                payload = self.http.get_json(
                    f"{CRYPTOQUANT_BASE_URL}{path}",
                    headers=headers,
                    params={"exchange": "all_exchange", "window": "hour", "limit": 3},
                )
                rows = _extract_series_rows(payload)
                leverage_ratio = max(
                    leverage_ratio,
                    _latest_value(rows, ("estimated_leverage_ratio", "value", "open_interest")),
                )
            except Exception:
                continue

        if leverage_ratio >= CRYPTOQUANT_OI_STRESS_SCORE:
            oi_stress = True

        whale_dump = inflow_btc >= CRYPTOQUANT_INFLOW_SPIKE_BTC
        result.update(
            {
                "ok": not errors or inflow_btc > 0 or oi_stress,
                "btc_exchange_inflow": round(inflow_btc, 4),
                "whale_dump_alert": whale_dump,
                "oi_stress": oi_stress,
                "estimated_leverage_ratio": round(leverage_ratio, 6),
                "reduce_spot_aggression": whale_dump,
                "external_exit_pressure": 0.85 if oi_stress else (0.55 if whale_dump else 0.0),
                "error": "; ".join(errors[:3]),
            }
        )
        self._cache.set(result)
        return result
