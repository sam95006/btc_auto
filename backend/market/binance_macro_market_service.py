"""Binance futures public metrics: long/short, taker flow, liquidations, spot-futures premium."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from backend.market.external_market_http import TimedCache
from config.external_market_config import (
    BINANCE_MACRO_ENABLED,
    BINANCE_MACRO_LIQ_STRESS_COUNT,
    BINANCE_MACRO_LONG_CROWDED,
    BINANCE_MACRO_REFRESH_SECONDS,
    BINANCE_MACRO_SHORT_CROWDED,
    BINANCE_MACRO_SPOT_PREMIUM_WARN_BPS,
    BINANCE_MACRO_SYMBOL,
)


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return float(default)


def _latest_ratio(rows: List[dict], key: str = "longShortRatio") -> float:
    if not rows:
        return 0.0
    row = rows[-1] if isinstance(rows[-1], dict) else {}
    return _safe_float(row.get(key) or row.get("buySellRatio"))


class BinanceMacroMarketService:
    def __init__(self, futures_client=None, spot_client=None):
        self.futures_client = futures_client
        self.spot_client = spot_client
        self._cache = TimedCache(BINANCE_MACRO_REFRESH_SECONDS)

    def configured(self) -> bool:
        return bool(
            BINANCE_MACRO_ENABLED
            and self.futures_client
            and getattr(self.futures_client, "is_configured", lambda: False)()
        )

    def fetch_btc_macro(self) -> Dict[str, Any]:
        cached = self._cache.get()
        if cached is not None:
            return cached

        symbol = BINANCE_MACRO_SYMBOL
        result: Dict[str, Any] = {
            "source": "binance_futures_macro",
            "configured": self.configured(),
            "ok": False,
            "symbol": symbol,
            "long_short_account_ratio": 0.0,
            "taker_buy_sell_ratio": 0.0,
            "open_interest": 0.0,
            "open_interest_change_pct": 0.0,
            "recent_liquidation_count": 0,
            "liquidation_stress": False,
            "long_crowded": False,
            "short_crowded": False,
            "spot_futures_premium_bps": 0.0,
            "spot_premium_elevated": False,
            "mark_price": 0.0,
            "index_price": 0.0,
            "error": "",
        }
        if not BINANCE_MACRO_ENABLED:
            result["error"] = "binance_macro_disabled"
            self._cache.set(result)
            return result
        if not self.configured():
            result["error"] = "binance_futures_not_configured"
            self._cache.set(result)
            return result

        errors: List[str] = []
        client = self.futures_client

        try:
            premium = client.get_premium_index(symbol) or {}
            mark = _safe_float(premium.get("markPrice"))
            index = _safe_float(premium.get("indexPrice"))
            result["mark_price"] = mark
            result["index_price"] = index
            if index > 0:
                basis_bps = ((mark - index) / index) * 10_000.0
                result["futures_basis_bps"] = round(basis_bps, 4)
        except Exception as exc:
            errors.append(f"premium:{exc}")

        try:
            oi = client.get_open_interest(symbol) or {}
            result["open_interest"] = _safe_float(oi.get("openInterest"))
        except Exception as exc:
            errors.append(f"oi:{exc}")

        for metric, field in (
            ("globalLongShortAccountRatio", "long_short_account_ratio"),
            ("takerlongshortRatio", "taker_buy_sell_ratio"),
        ):
            try:
                rows = client.get_futures_market_data(metric, symbol=symbol, period="1h", limit=3)
                result[field] = round(_latest_ratio(rows if isinstance(rows, list) else []), 6)
            except Exception as exc:
                errors.append(f"{metric}:{exc}")

        try:
            hist = client.get_futures_market_data("openInterestHist", symbol=symbol, period="1h", limit=3)
            if isinstance(hist, list) and len(hist) >= 2:
                prev = _safe_float(hist[-2].get("sumOpenInterest"))
                last = _safe_float(hist[-1].get("sumOpenInterest"))
                if prev > 0:
                    result["open_interest_change_pct"] = round((last - prev) / prev * 100.0, 4)
        except Exception as exc:
            errors.append(f"oi_hist:{exc}")

        liq_count = 0
        try:
            since_ms = int((time.time() - 3600) * 1000)
            orders = client.get_recent_liquidation_orders(symbol, limit=50, start_time=since_ms)
            if isinstance(orders, list):
                liq_count = len(orders)
        except Exception as exc:
            errors.append(f"liquidations:{exc}")

        result["recent_liquidation_count"] = liq_count
        result["liquidation_stress"] = liq_count >= BINANCE_MACRO_LIQ_STRESS_COUNT

        ls = _safe_float(result["long_short_account_ratio"])
        result["long_crowded"] = ls >= BINANCE_MACRO_LONG_CROWDED
        result["short_crowded"] = ls > 0 and ls <= BINANCE_MACRO_SHORT_CROWDED

        spot_premium_bps = 0.0
        if self.spot_client and getattr(self.spot_client, "is_configured", lambda: False)():
            try:
                spot_ticker = self.spot_client.get_book_ticker(symbol) or {}
                spot_mid = (
                    _safe_float(spot_ticker.get("bidPrice")) + _safe_float(spot_ticker.get("askPrice"))
                ) / 2.0
                mark = _safe_float(result.get("mark_price"))
                if spot_mid > 0 and mark > 0:
                    spot_premium_bps = ((spot_mid - mark) / mark) * 10_000.0
            except Exception as exc:
                errors.append(f"spot_premium:{exc}")
        result["spot_futures_premium_bps"] = round(spot_premium_bps, 4)
        result["spot_premium_elevated"] = abs(spot_premium_bps) >= BINANCE_MACRO_SPOT_PREMIUM_WARN_BPS

        result["ok"] = not errors or _safe_float(result["long_short_account_ratio"]) > 0
        result["error"] = "; ".join(errors[:4])
        self._cache.set(result)
        return result
