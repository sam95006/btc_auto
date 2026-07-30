"""Bybit Demo write client — api-demo.bybit.com only; no mainnet."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL

ALLOWED_WRITE_PATHS = frozenset(
    {
        "/v5/order/create",
        "/v5/order/cancel",
        "/v5/position/set-leverage",
    }
)
ALLOWED_PRIVATE_READ = frozenset(
    {
        "/v5/account/wallet-balance",
        "/v5/position/list",
        "/v5/order/realtime",
        "/v5/order/history",
        "/v5/position/closed-pnl",
    }
)
SMOKE_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT"})
HTTP_TIMEOUT = 20


class DemoWriteError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


def _float(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _round_qty(qty: float, step: float) -> str:
    if step <= 0:
        return f"{qty:.4f}".rstrip("0").rstrip(".")
    precision = max(0, int(round(-math.log10(step)))) if step < 1 else 0
    floored = math.floor(qty / step + 1e-12) * step
    return f"{floored:.{precision}f}".rstrip("0").rstrip(".") or "0"


def _round_price(price: float, tick: float) -> str:
    if tick <= 0:
        return f"{price:.2f}"
    precision = max(0, int(round(-math.log10(tick)))) if tick < 1 else 0
    rounded = round(round(price / tick) * tick, precision)
    return f"{rounded:.{precision}f}"


@dataclass
class DemoWriteClient:
    """Signed Demo REST client with hard domain + path guards."""

    api_key: str = ""
    api_secret: str = ""
    base_url: str = DEMO_REST_BASE_URL
    write_call_count: int = 0
    urls_called: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = (os.environ.get("BYBIT_DEMO_API_KEY") or "").strip()
        if not self.api_secret:
            self.api_secret = (os.environ.get("BYBIT_DEMO_API_SECRET") or "").strip()
        self.base_url = (self.base_url or DEMO_REST_BASE_URL).rstrip("/")
        self._assert_demo_scope()

    def _assert_demo_scope(self) -> None:
        if self.base_url != DEMO_REST_BASE_URL.rstrip("/"):
            raise DemoWriteError("mainnet_domain", self.base_url)
        if "api-demo.bybit.com" not in self.base_url:
            raise DemoWriteError("mainnet_domain", self.base_url)
        if (os.environ.get("MAINNET") or "").strip().lower() in {"1", "true", "yes"}:
            raise DemoWriteError("mainnet_flag")
        if (os.environ.get("REAL_MONEY") or "").strip().lower() in {"1", "true", "yes"}:
            raise DemoWriteError("real_money_flag")

    def _sign_headers(self, payload: str) -> dict[str, str]:
        if not self.api_key or not self.api_secret:
            raise DemoWriteError("credentials_missing")
        timestamp = str(int(time.time() * 1000))
        recv = "5000"
        sign = hmac.new(
            self.api_secret.encode("utf-8"),
            f"{timestamp}{self.api_key}{recv}{payload}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": sign,
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv,
            "User-Agent": "NEXUS-DemoValidation-Smoke/1.0",
        }

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if path not in ALLOWED_PRIVATE_READ:
            raise DemoWriteError("path_not_allowed", path)
        query = urlencode(sorted(params.items()))
        url = f"{self.base_url}{path}?{query}" if query else f"{self.base_url}{path}"
        headers = self._sign_headers(query)
        self.urls_called.append(path)
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("retCode") not in (0, "0", None):
            raise DemoWriteError("api_error", f"{data.get('retCode')}:{data.get('retMsg')}")
        return data

    def _post(self, path: str, body: dict[str, Any], *, count_write: bool = True) -> dict[str, Any]:
        if path not in ALLOWED_WRITE_PATHS:
            raise DemoWriteError("path_not_allowed", path)
        body_str = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        url = f"{self.base_url}{path}"
        headers = self._sign_headers(body_str)
        self.urls_called.append(path)
        if count_write:
            self.write_call_count += 1
        req = Request(url, data=body_str.encode("utf-8"), headers=headers, method="POST")
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("retCode") not in (0, "0", None):
            # leverage unchanged is OK
            if path == "/v5/position/set-leverage" and str(data.get("retCode")) == "110043":
                return data
            raise DemoWriteError("api_error", f"{data.get('retCode')}:{data.get('retMsg')}")
        return data

    def public_get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        query = urlencode(sorted(params.items()))
        url = f"{self.base_url}{path}?{query}"
        self.urls_called.append(path)
        req = Request(url, headers={"User-Agent": "NEXUS-DemoValidation-Smoke/1.0"}, method="GET")
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("retCode") not in (0, "0", None):
            raise DemoWriteError("public_api_error", f"{data.get('retCode')}:{data.get('retMsg')}")
        return data

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        symbol = symbol.upper()
        if symbol not in SMOKE_SYMBOLS:
            raise DemoWriteError("symbol_not_allowed", symbol)
        data = self.public_get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
        rows = (data.get("result") or {}).get("list") or []
        if not rows:
            raise DemoWriteError("ticker_missing", symbol)
        return rows[0]

    def fetch_klines(self, symbol: str, *, interval: str = "15", limit: int = 20) -> list[dict[str, Any]]:
        symbol = symbol.upper()
        if symbol not in SMOKE_SYMBOLS:
            raise DemoWriteError("symbol_not_allowed", symbol)
        data = self.public_get(
            "/v5/market/kline",
            {"category": "linear", "symbol": symbol, "interval": interval, "limit": str(limit)},
        )
        raw = (data.get("result") or {}).get("list") or []
        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, list) and len(item) >= 5:
                out.append(
                    {
                        "open": _float(item[1]),
                        "high": _float(item[2]),
                        "low": _float(item[3]),
                        "close": _float(item[4]),
                        "volume": _float(item[5]) if len(item) > 5 else 0.0,
                    }
                )
        return out

    def fetch_instrument(self, symbol: str) -> dict[str, Any]:
        symbol = symbol.upper()
        data = self.public_get("/v5/market/instruments-info", {"category": "linear", "symbol": symbol})
        rows = (data.get("result") or {}).get("list") or []
        if not rows:
            raise DemoWriteError("instrument_missing", symbol)
        return rows[0]

    def qty_step(self, info: dict[str, Any]) -> float:
        lot = info.get("lotSizeFilter") or {}
        return _float(lot.get("qtyStep") or lot.get("minOrderQty") or 0.001)

    def min_qty(self, info: dict[str, Any]) -> float:
        lot = info.get("lotSizeFilter") or {}
        return _float(lot.get("minOrderQty") or 0.0)

    def min_notional(self, info: dict[str, Any]) -> float:
        lot = info.get("lotSizeFilter") or {}
        return _float(lot.get("minNotionalValue") or lot.get("minOrderAmt") or 0.0)

    def tick_size(self, info: dict[str, Any]) -> float:
        pf = info.get("priceFilter") or {}
        return _float(pf.get("tickSize") or 0.01)

    def compute_qty(self, *, margin_usdt: float, leverage: int, price: float, info: dict[str, Any]) -> str:
        notional = margin_usdt * leverage
        raw_qty = notional / price if price > 0 else 0.0
        step = self.qty_step(info)
        qty_str = _round_qty(raw_qty, step)
        qty = _float(qty_str)
        if qty < self.min_qty(info):
            raise DemoWriteError("qty_below_min", qty_str)
        if self.min_notional(info) > 0 and qty * price < self.min_notional(info):
            raise DemoWriteError("notional_below_min", f"{qty * price}")
        if qty <= 0:
            raise DemoWriteError("qty_invalid", qty_str)
        return qty_str

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        body = {
            "category": "linear",
            "symbol": symbol.upper(),
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage),
        }
        return self._post("/v5/position/set-leverage", body, count_write=True)

    def create_market_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: str,
        order_link_id: str,
        stop_loss: str,
        take_profit: str,
    ) -> dict[str, Any]:
        body = {
            "category": "linear",
            "symbol": symbol.upper(),
            "side": side,
            "orderType": "Market",
            "qty": qty,
            "orderLinkId": order_link_id[:36],
            "stopLoss": stop_loss,
            "takeProfit": take_profit,
            "tpslMode": "Full",
            "slTriggerBy": "LastPrice",
            "tpTriggerBy": "LastPrice",
            "positionIdx": 0,
        }
        return self._post("/v5/order/create", body)

    def cancel_order(self, *, symbol: str, order_id: str = "", order_link_id: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {"category": "linear", "symbol": symbol.upper()}
        if order_id:
            body["orderId"] = order_id
        if order_link_id:
            body["orderLinkId"] = order_link_id
        return self._post("/v5/order/cancel", body)

    def close_reduce_only(self, *, symbol: str, side: str, qty: str, order_link_id: str) -> dict[str, Any]:
        close_side = "Sell" if side.lower() == "buy" else "Buy"
        body = {
            "category": "linear",
            "symbol": symbol.upper(),
            "side": close_side,
            "orderType": "Market",
            "qty": qty,
            "reduceOnly": True,
            "orderLinkId": order_link_id[:36],
            "positionIdx": 0,
        }
        return self._post("/v5/order/create", body)

    def list_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"category": "linear", "settleCoin": "USDT"}
        if symbol:
            params["symbol"] = symbol.upper()
        data = self._get("/v5/position/list", params)
        rows = (data.get("result") or {}).get("list") or []
        return [r for r in rows if abs(_float(r.get("size"))) > 0]

    def list_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"category": "linear", "settleCoin": "USDT"}
        if symbol:
            params["symbol"] = symbol.upper()
        data = self._get("/v5/order/realtime", params)
        return list((data.get("result") or {}).get("list") or [])

    def closed_pnl(self, symbol: str) -> dict[str, Any] | None:
        data = self._get(
            "/v5/position/closed-pnl",
            {"category": "linear", "symbol": symbol.upper(), "limit": "5"},
        )
        rows = (data.get("result") or {}).get("list") or []
        return rows[0] if rows else None

    @staticmethod
    def format_price(price: float, tick: float) -> str:
        return _round_price(price, tick)
