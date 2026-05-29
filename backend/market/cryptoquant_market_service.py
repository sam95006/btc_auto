"""CryptoQuant: exchange inflow whale alert + futures OI stress (advisory)."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.market.external_market_http import ExternalMarketHttp, TimedCache
from config.external_market_config import (
    CRYPTOQUANT_API_KEY,
    CRYPTOQUANT_BASE_URL,
    CRYPTOQUANT_INFLOW_SPIKE_BTC,
    CRYPTOQUANT_NETFLOW_BEARISH_BTC,
    CRYPTOQUANT_OI_STRESS_SCORE,
    CRYPTOQUANT_OUTFLOW_SPIKE_BTC,
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
            "btc_exchange_outflow": 0.0,
            "btc_exchange_netflow": 0.0,
            "whale_dump_alert": False,
            "whale_withdrawal_alert": False,
            "netflow_bearish": False,
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
        outflow_btc = 0.0
        netflow_btc = 0.0
        oi_stress = False
        errors: List[str] = []

        flow_specs = (
            ("/btc/exchange-flows/inflow", "inflow", ("inflow_total", "value", "inflow")),
            ("/btc/exchange-flows/inflow-total", "inflow", ("inflow_total", "value", "inflow")),
            ("/btc/exchange-flows/outflow", "outflow", ("outflow_total", "value", "outflow")),
            ("/btc/exchange-flows/outflow-total", "outflow", ("outflow_total", "value", "outflow")),
            ("/btc/exchange-flows/netflow", "netflow", ("netflow_total", "value", "netflow")),
            ("/btc/exchange-flows/netflow-total", "netflow", ("netflow_total", "value", "netflow")),
        )
        for path, kind, keys in flow_specs:
            try:
                payload = self.http.get_json(
                    f"{CRYPTOQUANT_BASE_URL}{path}",
                    headers=headers,
                    params={"exchange": "all_exchange", "window": "hour", "limit": 3},
                )
                rows = _extract_series_rows(payload)
                val = _latest_value(rows, keys)
                if val <= 0:
                    continue
                if kind == "inflow" and not inflow_btc:
                    inflow_btc = val
                elif kind == "outflow" and not outflow_btc:
                    outflow_btc = val
                elif kind == "netflow" and not netflow_btc:
                    netflow_btc = val
            except Exception as exc:
                errors.append(f"{path}:{exc}")

        if not netflow_btc and (inflow_btc or outflow_btc):
            netflow_btc = inflow_btc - outflow_btc

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
        whale_withdrawal = outflow_btc >= CRYPTOQUANT_OUTFLOW_SPIKE_BTC
        netflow_bearish = netflow_btc >= CRYPTOQUANT_NETFLOW_BEARISH_BTC
        exit_pressure = 0.0
        if oi_stress:
            exit_pressure = 0.85
        elif whale_dump or netflow_bearish:
            exit_pressure = 0.55
        elif whale_withdrawal:
            exit_pressure = 0.35
        result.update(
            {
                "ok": not errors or inflow_btc > 0 or outflow_btc > 0 or oi_stress,
                "btc_exchange_inflow": round(inflow_btc, 4),
                "btc_exchange_outflow": round(outflow_btc, 4),
                "btc_exchange_netflow": round(netflow_btc, 4),
                "whale_dump_alert": whale_dump,
                "whale_withdrawal_alert": whale_withdrawal,
                "netflow_bearish": netflow_bearish,
                "oi_stress": oi_stress,
                "estimated_leverage_ratio": round(leverage_ratio, 6),
                "reduce_spot_aggression": whale_dump or netflow_bearish,
                "external_exit_pressure": exit_pressure,
                "error": "; ".join(errors[:5]),
            }
        )
        self._cache.set(result)
        return result
