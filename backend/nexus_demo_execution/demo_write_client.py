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
        "/v5/account/info",
        "/v5/user/query-api",
        "/v5/position/list",
        "/v5/order/realtime",
        "/v5/order/history",
        "/v5/position/closed-pnl",
        "/v5/account/fee-rate",
        "/v5/account/transaction-log",
        "/v5/execution/list",
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


def _step_decimals(step: float) -> int:
    """Deterministic decimal places for qty/price steps (handles non-power-of-10 ticks)."""
    if step <= 0:
        return 4
    # Normalize via integer scaling to avoid float log10 edge cases (e.g. 0.00015).
    text = f"{step:.16f}".rstrip("0").rstrip(".")
    if "." not in text:
        return 0
    return len(text.split(".", 1)[1])


def _round_qty(qty: float, step: float) -> str:
    if step <= 0:
        return f"{qty:.4f}".rstrip("0").rstrip(".")
    precision = _step_decimals(step)
    floored = math.floor(qty / step + 1e-12) * step
    out = f"{floored:.{precision}f}"
    # Preserve exact step precision for exchange validation; strip only pure trailing zeros beyond step.
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return out or "0"


def _round_price(price: float, tick: float) -> str:
    if tick <= 0:
        return f"{price:.2f}"
    precision = _step_decimals(tick)
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
        info = rows[0]
        status = str(info.get("status") or "").strip()
        if status and status.upper() not in {"TRADING", "AVAILABLE", ""}:
            raise DemoWriteError("instrument_status_invalid", f"{symbol}:{status}")
        return info

    def qty_step(self, info: dict[str, Any]) -> float:
        lot = info.get("lotSizeFilter") or {}
        raw = lot.get("qtyStep")
        if raw is None or raw == "":
            raw = lot.get("minOrderQty")
        step = _float(raw) if raw not in (None, "") else 0.0
        if step <= 0:
            raise DemoWriteError("qty_step", f"missing_or_invalid:{raw!r}")
        return step

    def min_qty(self, info: dict[str, Any]) -> float:
        lot = info.get("lotSizeFilter") or {}
        return _float(lot.get("minOrderQty") or 0.0)

    def min_notional(self, info: dict[str, Any]) -> float:
        lot = info.get("lotSizeFilter") or {}
        return _float(lot.get("minNotionalValue") or lot.get("minOrderAmt") or 0.0)

    def tick_size(self, info: dict[str, Any]) -> float:
        pf = info.get("priceFilter") or {}
        tick = _float(pf.get("tickSize") or 0.0)
        if tick <= 0:
            raise DemoWriteError("price_tick", "missing_or_invalid")
        return tick

    def compute_qty(self, *, margin_usdt: float, leverage: int, price: float, info: dict[str, Any]) -> str:
        if price <= 0:
            raise DemoWriteError("qty_invalid", "price_non_positive")
        notional = float(margin_usdt) * int(leverage)
        raw_qty = notional / price
        step = self.qty_step(info)
        qty_str = _round_qty(raw_qty, step)
        qty = _float(qty_str)
        if qty <= 0:
            # Floor-to-zero after step rounding under high mark / fixed margin.
            raise DemoWriteError(
                "qty_step_rounding",
                f"raw={raw_qty:.12g};step={step};rounded={qty_str}",
            )
        min_q = self.min_qty(info)
        if min_q > 0 and qty + 1e-15 < min_q:
            raise DemoWriteError("qty_below_min", f"{qty_str}<{min_q}")
        min_n = self.min_notional(info)
        if min_n > 0 and qty * price + 1e-12 < min_n:
            raise DemoWriteError("notional_below_min", f"{qty * price}<{min_n}")
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

    def fetch_fee_rate_quote(self, symbol: str):
        """Resolve taker fee with honest status — never invent silent zeros.

        Domain is locked to api-demo.bybit.com by DemoWriteClient guards.
        Never fall back to mainnet/testnet for fee discovery.
        """
        from backend.nexus_demo_execution.fee_rate import (
            DEMO_FEE_ENDPOINT_UNSUPPORTED,
            cache_get,
            classify_demo_fee_error,
            configured_conservative_quote,
            parse_fee_rows,
            unavailable,
        )

        symbol = symbol.upper()
        cached = cache_get(symbol)
        if cached is not None:
            return cached

        try:
            data = self._get(
                "/v5/account/fee-rate",
                {"category": "linear", "symbol": symbol},
            )
            rows = (data.get("result") or {}).get("list") or []
            quote = parse_fee_rows(rows, symbol)
            if quote.usable_taker is not None:
                return quote
            data2 = self._get("/v5/account/fee-rate", {"category": "linear"})
            rows2 = (data2.get("result") or {}).get("list") or []
            quote2 = parse_fee_rows(rows2, symbol)
            if quote2.usable_taker is not None:
                quote2.fee_source = "bybit_demo:/v5/account/fee-rate?category=linear"
                return quote2
            if quote2.status == DEMO_FEE_ENDPOINT_UNSUPPORTED or quote.status == DEMO_FEE_ENDPOINT_UNSUPPORTED:
                cons = configured_conservative_quote(symbol)
                return cons or quote2
            conservative = configured_conservative_quote(symbol)
            return conservative or quote2
        except DemoWriteError as exc:
            status = classify_demo_fee_error(exc.code, exc.detail)
            conservative = configured_conservative_quote(symbol)
            if conservative is not None:
                conservative.fee_fetch_error = f"{exc.code}:{exc.detail}"
                return conservative
            return unavailable(symbol, status=status, error=f"{exc.code}:{exc.detail}")
        except Exception as exc:  # noqa: BLE001
            conservative = configured_conservative_quote(symbol)
            if conservative is not None:
                conservative.fee_fetch_error = type(exc).__name__
                return conservative
            return unavailable(symbol, error=type(exc).__name__)

    def fetch_fee_rate(self, symbol: str) -> float | None:
        """Backward-compatible taker rate or None (must not invent)."""
        return self.fetch_fee_rate_quote(symbol).usable_taker

    def api_key_fingerprint(self) -> str:
        """SHA256 prefix of API key — never return raw key."""
        raw = (self.api_key or "").strip()
        if not raw:
            return ""
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def fetch_wallet_snapshot(self, *, coin: str = "USDT", account_type: str = "UNIFIED") -> dict[str, Any]:
        """Official Demo wallet/account snapshot for settle coin — full precision strings."""
        data = self._get(
            "/v5/account/wallet-balance",
            {"accountType": account_type, "coin": coin.upper()},
        )
        rows = (data.get("result") or {}).get("list") or []
        if not rows:
            raise DemoWriteError("empty_wallet_balance_response")
        account = rows[0]
        coins = account.get("coin") or []
        usdt = next((c for c in coins if str(c.get("coin", "")).upper() == coin.upper()), None) or {}
        ts = int(time.time() * 1000)
        return {
            "ts_ms": ts,
            "exchange_domain": "api-demo.bybit.com",
            "account_type": str(account.get("accountType") or account_type),
            "wallet_type": "UNIFIED" if str(account.get("accountType") or account_type).upper() == "UNIFIED" else str(account.get("accountType") or account_type),
            "settle_coin": coin.upper(),
            "category": "linear",
            "wallet_balance": str(usdt.get("walletBalance") if usdt.get("walletBalance") not in (None, "") else account.get("totalWalletBalance") or "0"),
            "equity": str(account.get("totalEquity") or usdt.get("equity") or "0"),
            "available_balance": str(
                usdt.get("availableToWithdraw")
                or usdt.get("availableBalance")
                or usdt.get("walletBalance")
                or "0"
            ),
            "coin_balance": str(usdt.get("walletBalance") or "0"),
            "total_wallet_balance": str(account.get("totalWalletBalance") or "0"),
            "total_equity": str(account.get("totalEquity") or "0"),
            "unrealized_pnl": str(account.get("totalPerpUPL") or usdt.get("unrealisedPnl") or "0"),
            "api_key_fingerprint": self.api_key_fingerprint(),
            "source_endpoint": "/v5/account/wallet-balance",
        }

    def fetch_account_identity(self) -> dict[str, Any]:
        """Demo account type / UID where API exposes safely — hash key only."""
        out: dict[str, Any] = {
            "exchange_domain": "api-demo.bybit.com",
            "api_key_fingerprint": self.api_key_fingerprint(),
            "account_uid": None,
            "account_type": None,
            "unifiedMarginStatus": None,
            "dcpStatus": None,
            "isMasterTrader": None,
            "wallet_context": "UNKNOWN",
            "source_endpoints": [],
        }
        try:
            info = self._get("/v5/account/info", {})
            res = info.get("result") or {}
            out["account_type"] = res.get("accountType") or res.get("unifiedMarginStatus")
            out["unifiedMarginStatus"] = res.get("unifiedMarginStatus")
            out["dcpStatus"] = res.get("dcpStatus")
            out["isMasterTrader"] = res.get("isMasterTrader")
            out["source_endpoints"].append("/v5/account/info")
            ums = str(res.get("unifiedMarginStatus") or "")
            if ums in {"1", "3", "4", "5", "6"} or str(res.get("accountType") or "").upper() == "UNIFIED":
                out["wallet_context"] = "UNIFIED"
            elif ums:
                out["wallet_context"] = f"UNIFIED_STATUS_{ums}"
        except DemoWriteError as exc:
            out["account_info_error"] = exc.code
        try:
            api = self._get("/v5/user/query-api", {})
            res = api.get("result") or {}
            # Prefer numeric uid fields; never store secrets
            uid = res.get("userID") or res.get("uid") or res.get("parentUid") or res.get("memberId")
            if uid is not None:
                out["account_uid"] = str(uid)
            out["read_only"] = res.get("readOnly")
            out["vip_level"] = res.get("vipLevel")
            out["source_endpoints"].append("/v5/user/query-api")
            if res.get("uta") or res.get("utaAccount"):
                out["wallet_context"] = "UNIFIED"
        except DemoWriteError as exc:
            out["query_api_error"] = exc.code
        # Wallet type cross-check
        try:
            snap = self.fetch_wallet_snapshot()
            out["account_type"] = out["account_type"] or snap.get("account_type")
            out["wallet_type"] = snap.get("wallet_type")
            out["settle_coin"] = snap.get("settle_coin")
            if snap.get("wallet_type") == "UNIFIED":
                out["wallet_context"] = "UNIFIED"
            out["wallet_balance"] = snap.get("wallet_balance")
            out["equity"] = snap.get("equity")
            out["available_balance"] = snap.get("available_balance")
            out["source_endpoints"].append("/v5/account/wallet-balance")
        except DemoWriteError as exc:
            out["wallet_error"] = exc.code
        return out

    def list_closed_pnl(self, *, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"category": "linear", "limit": str(max(1, min(100, int(limit))))}
        if symbol:
            params["symbol"] = symbol.upper()
        data = self._get("/v5/position/closed-pnl", params)
        return list((data.get("result") or {}).get("list") or [])

    def list_executions(self, *, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"category": "linear", "limit": str(max(1, min(100, int(limit))))}
        if symbol:
            params["symbol"] = symbol.upper()
        data = self._get("/v5/execution/list", params)
        return list((data.get("result") or {}).get("list") or [])

    def list_transaction_log(self, *, limit: int = 50, coin: str = "USDT") -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "accountType": "UNIFIED",
            "category": "linear",
            "currency": coin,
            "limit": str(max(1, min(100, int(limit)))),
        }
        data = self._get("/v5/account/transaction-log", params)
        return list((data.get("result") or {}).get("list") or [])

    def _paginate_get(
        self,
        path: str,
        base_params: dict[str, Any],
        *,
        max_pages: int = 10,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        """Bounded cursor pagination for private history endpoints."""
        rows: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(max(1, min(20, int(max_pages)))):
            params = dict(base_params)
            if start_time_ms is not None:
                params["startTime"] = str(int(start_time_ms))
            if end_time_ms is not None:
                params["endTime"] = str(int(end_time_ms))
            if cursor:
                params["cursor"] = cursor
            data = self._get(path, params)
            result = data.get("result") or {}
            batch = list(result.get("list") or [])
            rows.extend(r for r in batch if isinstance(r, dict))
            cursor = str(result.get("nextPageCursor") or "")
            if not cursor or not batch:
                break
        return rows

    def list_closed_pnl_paginated(
        self,
        *,
        symbol: str | None = None,
        limit: int = 100,
        max_pages: int = 10,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"category": "linear", "limit": str(max(1, min(100, int(limit))))}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._paginate_get(
            "/v5/position/closed-pnl",
            params,
            max_pages=max_pages,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )

    def list_executions_paginated(
        self,
        *,
        symbol: str | None = None,
        limit: int = 100,
        max_pages: int = 10,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"category": "linear", "limit": str(max(1, min(100, int(limit))))}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._paginate_get(
            "/v5/execution/list",
            params,
            max_pages=max_pages,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )

    def list_transaction_log_paginated(
        self,
        *,
        limit: int = 100,
        coin: str = "USDT",
        max_pages: int = 10,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "accountType": "UNIFIED",
            "category": "linear",
            "currency": coin,
            "limit": str(max(1, min(100, int(limit)))),
        }
        return self._paginate_get(
            "/v5/account/transaction-log",
            params,
            max_pages=max_pages,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )

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
