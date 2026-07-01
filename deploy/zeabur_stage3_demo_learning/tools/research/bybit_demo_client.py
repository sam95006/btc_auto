"""Bybit demo/testnet client with hard safety guards (Stage 3)."""
from __future__ import annotations

import math
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tools.research.bybit_demo_learning_common import (
    BYBIT_DEMO_BASE_URL,
    BYBIT_MAINNET_BASE_URL,
    MAX_LEVERAGE,
    MAX_MARGIN_USD,
    MAX_OPEN_POSITIONS,
    utc_now_iso,
)

ALLOWED_MODES = frozenset({"mock", "dry-run", "demo-order"})
FORBIDDEN_PATH_FRAGMENTS = (
    "/v5/asset/withdraw",
    "/v5/asset/transfer",
    "/v5/asset/inter-transfer",
    "/v5/asset/deposit",
    "/v5/order",
    "/v5/position/close",
    "/v5/position/trading-stop",
)
ALLOWED_PRIVATE_READ_PATHS = (
    "/v5/account/wallet-balance",
    "/v5/position/list",
    "/v5/position/closed-pnl",
)
ALLOWED_PRIVATE_WRITE_PATHS = (
    "/v5/order/create",
    "/v5/position/set-leverage",
)
DEFAULT_SYMBOL = "ETHUSDT"
STAGE4_READ_ONLY_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"})
DEFAULT_CATEGORY = "linear"
DEFAULT_COIN = "USDT"
DEFAULT_ACCOUNT_TYPE = "UNIFIED"
HTTP_TIMEOUT = 20
DEFAULT_MAX_HOLD_MINUTES = 10
DEFAULT_STOP_LOSS_MAX_USD = 2.0
SAFE_BALANCE_FRACTION = 0.5


def _round_qty(qty: float, step: float) -> str:
    if step <= 0:
        return f"{qty:.4f}".rstrip("0").rstrip(".")
    precision = max(0, int(round(-math.log10(step)))) if step < 1 else 0
    floored = math.floor(qty / step) * step
    return f"{floored:.{precision}f}".rstrip("0").rstrip(".") or "0"


def _round_price(price: float, tick: float) -> str:
    if tick <= 0:
        return f"{price:.2f}"
    precision = max(0, int(round(-math.log10(tick)))) if tick < 1 else 0
    rounded = round(round(price / tick) * tick, precision)
    return f"{rounded:.{precision}f}"


class BybitDemoClientError(Exception):
    pass


class DemoOrderNotAllowedError(BybitDemoClientError):
    """demo-order mode blocked until operator GO."""


class MainnetBlockedError(BybitDemoClientError):
    pass


class SafetyCapViolation(BybitDemoClientError):
    pass


@dataclass
class OrderIntent:
    symbol: str
    side: str
    qty: float
    price: float
    stop_loss: float
    max_hold_seconds: int
    leverage: int
    margin_usd: float
    category: str = DEFAULT_CATEGORY

    def validate(self) -> None:
        if self.symbol.upper() != DEFAULT_SYMBOL:
            raise SafetyCapViolation(f"symbol_not_allowed:{self.symbol}")
        if self.category != DEFAULT_CATEGORY:
            raise SafetyCapViolation(f"category_not_allowed:{self.category}")
        if self.margin_usd > MAX_MARGIN_USD:
            raise SafetyCapViolation("margin_usd_exceeds_cap")
        if self.leverage > MAX_LEVERAGE:
            raise SafetyCapViolation("leverage_exceeds_cap")
        if self.stop_loss <= 0:
            raise SafetyCapViolation("missing_stop_loss")
        if self.max_hold_seconds <= 0:
            raise SafetyCapViolation("missing_max_hold")


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _float_val(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def assert_demo_scope() -> None:
    base = (os.environ.get("BYBIT_M0_BASE_URL") or BYBIT_DEMO_BASE_URL).strip().rstrip("/")
    if base.rstrip("/") == BYBIT_MAINNET_BASE_URL.rstrip("/"):
        raise MainnetBlockedError("bybit_mainnet_detected")
    if "api.bybit.com" in base and "api-demo.bybit.com" not in base:
        raise MainnetBlockedError("bybit_mainnet_detected")
    if _truthy(os.environ.get("BYBIT_MAINNET_ALLOWED")):
        raise MainnetBlockedError("bybit_mainnet_allowed_true")
    if _truthy(os.environ.get("REAL_MONEY")):
        raise MainnetBlockedError("real_money_detected")
    scope = (os.environ.get("BYBIT_ORDER_SCOPE") or "").strip()
    if scope and scope != "demo_or_testnet_only":
        raise BybitDemoClientError(f"invalid_order_scope:{scope}")


def _assert_private_path(path: str, *, write: bool = False) -> None:
    allowed = ALLOWED_PRIVATE_WRITE_PATHS if write else ALLOWED_PRIVATE_READ_PATHS
    if not any(path.startswith(p) or p in path for p in allowed):
        raise BybitDemoClientError(f"private_{'write' if write else 'read'}_path_not_allowed:{path}")


def _assert_url_allowed(url: str, *, private: bool = False, write: bool = False) -> None:
    lower = url.lower()
    if "api.bybit.com" in lower and "api-demo.bybit.com" not in lower:
        raise MainnetBlockedError(f"mainnet_url_blocked:{url}")
    for frag in FORBIDDEN_PATH_FRAGMENTS:
        if frag in lower and not (write and frag == "/v5/order" and "/v5/order/create" in lower):
            if write and "/v5/order/create" in lower:
                continue
            if not private:
                raise BybitDemoClientError(f"forbidden_endpoint:{frag}")
    if private:
        path = url.split("?", 1)[0].replace(lower.split("api-demo.bybit.com")[-1].split(".com")[-1] if "api-demo" in lower else "", "")
        # extract path after host
        if "api-demo.bybit.com" in lower:
            path = "/" + lower.split("api-demo.bybit.com/", 1)[-1].split("?", 1)[0]
        else:
            path = "/" + lower.split(".com/", 1)[-1].split("?", 1)[0] if ".com/" in lower else lower
        _assert_private_path(path, write=write)


def _http_get_json(url: str) -> Dict[str, Any]:
    _assert_url_allowed(url, private=False)
    req = Request(url, headers={"User-Agent": "NEXUS-Stage3DemoLearning/1.0"})
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


class BybitDemoClient:
    """Demo/testnet client; mock and dry-run never submit exchange orders."""

    def __init__(self, mode: str, *, allow_demo_order: bool = False) -> None:
        mode = mode.strip().lower()
        if mode not in ALLOWED_MODES:
            raise BybitDemoClientError(f"invalid_mode:{mode}")
        if mode == "demo-order" and not allow_demo_order:
            raise DemoOrderNotAllowedError(
                "demo-order mode requires explicit operator GO; use mock or dry-run"
            )
        self.mode = mode
        env_base = (os.environ.get("BYBIT_M0_BASE_URL") or BYBIT_DEMO_BASE_URL).strip().rstrip("/")
        self.base_url = env_base if env_base else BYBIT_DEMO_BASE_URL.rstrip("/")
        self.open_positions = 0
        self.urls_called: List[str] = []
        self._last_account: Dict[str, Any] = {}
        assert_demo_scope()

    def _api_key(self) -> str:
        return os.environ.get("BYBIT_DEMO_API_KEY", "").strip()

    def _api_secret(self) -> str:
        return os.environ.get("BYBIT_DEMO_API_SECRET", "").strip()

    def _signed_get(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        key = self._api_key()
        secret = self._api_secret()
        if not key or not secret:
            raise BybitDemoClientError("missing_demo_credentials")
        query = urlencode(sorted(params.items()))
        url = f"{self.base_url}{path}?{query}" if query else f"{self.base_url}{path}"
        if "api-demo.bybit.com" not in url and self.base_url not in url:
            raise MainnetBlockedError(f"mainnet_url_blocked:{url}")
        _assert_private_path(path, write=False)
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        sign_payload = f"{timestamp}{key}{recv_window}{query}"
        signature = hmac.new(secret.encode(), sign_payload.encode(), hashlib.sha256).hexdigest()
        headers = {
            "User-Agent": "NEXUS-Stage3DemoLearning/1.0",
            "X-BAPI-API-KEY": key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
        }
        self.urls_called.append(url)
        req = Request(url, headers=headers)
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("retCode") not in (0, "0", None):
            raise BybitDemoClientError(f"bybit_api_error:{payload.get('retCode')}:{payload.get('retMsg')}")
        return payload

    def _signed_post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if self.mode != "demo-order":
            raise BybitDemoClientError("signed_post_forbidden_outside_demo_order")
        key = self._api_key()
        secret = self._api_secret()
        if not key or not secret:
            raise BybitDemoClientError("missing_demo_credentials")
        _assert_private_path(path, write=True)
        url = f"{self.base_url}{path}"
        if "api-demo.bybit.com" not in self.base_url:
            raise MainnetBlockedError("bybit_mainnet_detected")
        body_str = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        sign_payload = f"{timestamp}{key}{recv_window}{body_str}"
        signature = hmac.new(secret.encode(), sign_payload.encode(), hashlib.sha256).hexdigest()
        headers = {
            "User-Agent": "NEXUS-Stage3DemoLearning/1.0",
            "Content-Type": "application/json",
            "X-BAPI-API-KEY": key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
        }
        self.urls_called.append(url)
        req = Request(url, data=body_str.encode("utf-8"), headers=headers, method="POST")
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("retCode") not in (0, "0", None):
            raise BybitDemoClientError(f"bybit_api_error:{payload.get('retCode')}:{payload.get('retMsg')}")
        return payload

    def _mock_balance(self) -> Dict[str, Any]:
        return {
            "snapshot_id": str(uuid.uuid4()),
            "ts": utc_now_iso(),
            "source": "bybit_demo",
            "account_type": DEFAULT_ACCOUNT_TYPE,
            "coin": DEFAULT_COIN,
            "total_equity": 1000.0,
            "wallet_balance": 1000.0,
            "available_balance": 950.0,
            "used_margin": 50.0,
            "unrealized_pnl": 0.0,
            "max_margin_usd": MAX_MARGIN_USD,
            "max_leverage": MAX_LEVERAGE,
            "max_open_positions": MAX_OPEN_POSITIONS,
            "max_allowed_margin": min(MAX_MARGIN_USD, 950.0 * SAFE_BALANCE_FRACTION),
            "balance_read_ok": True,
            "mainnet_detected": False,
            "real_money_detected": False,
            "wallet_coin_missing": False,
            "mode": self.mode,
        }

    def _parse_wallet_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        rows = ((payload.get("result") or {}).get("list") or [])
        if not rows:
            raise BybitDemoClientError("empty_wallet_balance_response")
        account = rows[0]
        coins = account.get("coin") or []
        usdt = next((c for c in coins if str(c.get("coin", "")).upper() == DEFAULT_COIN), None)
        wallet_coin_missing = usdt is None
        total_equity = _float_val(account.get("totalEquity"))
        wallet_balance = _float_val(usdt.get("walletBalance")) if usdt else 0.0
        available_balance = _float_val(
            (usdt or {}).get("availableToWithdraw")
            or (usdt or {}).get("availableBalance")
            or (usdt or {}).get("equity")
        )
        if usdt and available_balance == 0.0:
            available_balance = _float_val(usdt.get("walletBalance"))
        used_margin = _float_val((usdt or {}).get("totalPositionIM") or account.get("totalInitialMargin"))
        unrealized_pnl = _float_val((usdt or {}).get("unrealisedPnl"))
        if total_equity == 0.0 and wallet_balance > 0:
            total_equity = wallet_balance + unrealized_pnl
        max_allowed = min(MAX_MARGIN_USD, available_balance * SAFE_BALANCE_FRACTION)
        return {
            "snapshot_id": str(uuid.uuid4()),
            "ts": utc_now_iso(),
            "source": "bybit_demo",
            "account_type": account.get("accountType") or DEFAULT_ACCOUNT_TYPE,
            "coin": DEFAULT_COIN,
            "total_equity": round(total_equity, 6),
            "wallet_balance": round(wallet_balance, 6),
            "available_balance": round(available_balance, 6),
            "used_margin": round(used_margin, 6),
            "unrealized_pnl": round(unrealized_pnl, 6),
            "max_margin_usd": MAX_MARGIN_USD,
            "max_leverage": MAX_LEVERAGE,
            "max_open_positions": MAX_OPEN_POSITIONS,
            "max_allowed_margin": round(max_allowed, 6),
            "balance_read_ok": not wallet_coin_missing,
            "mainnet_detected": False,
            "real_money_detected": _truthy(os.environ.get("REAL_MONEY")),
            "wallet_coin_missing": wallet_coin_missing,
            "mode": self.mode,
        }

    def get_account_balance(self, coin: str = DEFAULT_COIN) -> Dict[str, Any]:
        if self.mode == "mock":
            self._last_account = self._mock_balance()
            return dict(self._last_account)
        params = {"accountType": DEFAULT_ACCOUNT_TYPE, "coin": coin.upper()}
        payload = self._signed_get("/v5/account/wallet-balance", params)
        self._last_account = self._parse_wallet_payload(payload)
        return dict(self._last_account)

    def get_wallet_balance(self, coin: str = DEFAULT_COIN) -> float:
        acct = self.get_account_balance(coin=coin)
        return float(acct.get("wallet_balance") or 0.0)

    def get_available_balance(self, coin: str = DEFAULT_COIN) -> float:
        acct = self.get_account_balance(coin=coin)
        return float(acct.get("available_balance") or 0.0)

    def list_open_positions(
        self,
        symbol: str = DEFAULT_SYMBOL,
        category: str = DEFAULT_CATEGORY,
    ) -> List[Dict[str, Any]]:
        if self.mode == "mock":
            return []
        params = {"category": category, "symbol": symbol.upper()}
        payload = self._signed_get("/v5/position/list", params)
        rows = ((payload.get("result") or {}).get("list") or [])
        open_rows: List[Dict[str, Any]] = []
        for row in rows:
            size = abs(_float_val(row.get("size")))
            if size > 0:
                open_rows.append(row)
        return open_rows

    def count_open_positions(
        self,
        symbol: str = DEFAULT_SYMBOL,
        category: str = DEFAULT_CATEGORY,
    ) -> int:
        return len(self.list_open_positions(symbol=symbol, category=category))

    def fetch_ticker(self, symbol: str = DEFAULT_SYMBOL) -> Dict[str, Any]:
        symbol = symbol.upper()
        read_allowed = symbol in STAGE4_READ_ONLY_SYMBOLS
        if symbol != DEFAULT_SYMBOL and not read_allowed:
            raise SafetyCapViolation(f"symbol_not_allowed:{symbol}")
        if self.mode == "mock":
            ts = int(time.time())
            base = 3200.0 + (ts % 17) if symbol == "ETHUSDT" else 65000.0 + (ts % 37)
            prev = base * 0.998
            return {
                "symbol": symbol,
                "lastPrice": str(base),
                "prevPrice24h": str(prev),
                "highPrice24h": str(base * 1.002),
                "lowPrice24h": str(base * 0.996),
                "volume24h": "1000",
                "turnover24h": str(base * 1000),
                "bid1Price": str(base - 0.5),
                "ask1Price": str(base + 0.5),
                "source": "mock",
            }
        params = {"category": DEFAULT_CATEGORY, "symbol": symbol}
        url = f"{self.base_url}/v5/market/tickers?{urlencode(params)}"
        self.urls_called.append(url)
        payload = _http_get_json(url)
        items = ((payload.get("result") or {}).get("list") or [])
        if not items:
            raise RuntimeError("empty_ticker_response")
        row = items[0]
        row["source"] = "bybit_demo_public_ticker"
        return row

    def fetch_klines(
        self,
        symbol: str,
        *,
        interval: str = "15",
        limit: int = 20,
        category: str = DEFAULT_CATEGORY,
    ) -> List[Dict[str, Any]]:
        """Read-only public klines for Stage 4 market context."""
        symbol = symbol.upper()
        if symbol not in STAGE4_READ_ONLY_SYMBOLS:
            raise SafetyCapViolation(f"symbol_not_allowed:{symbol}")
        if self.mode == "mock":
            base = 3200.0 if symbol == "ETHUSDT" else 65000.0
            rows: List[Dict[str, Any]] = []
            for i in range(min(limit, 20)):
                px = base + i * 0.5
                rows.append({"open": px, "high": px + 1, "low": px - 1, "close": px + 0.2, "volume": 10})
            return rows
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": str(min(max(limit, 1), 200)),
        }
        url = f"{self.base_url}/v5/market/kline?{urlencode(params)}"
        self.urls_called.append(url)
        payload = _http_get_json(url)
        raw = ((payload.get("result") or {}).get("list") or [])
        out: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, list) and len(item) >= 5:
                out.append(
                    {
                        "open": _float_val(item[1]),
                        "high": _float_val(item[2]),
                        "low": _float_val(item[3]),
                        "close": _float_val(item[4]),
                        "volume": _float_val(item[5]) if len(item) > 5 else 0.0,
                    }
                )
            elif isinstance(item, dict):
                out.append(
                    {
                        "open": _float_val(item.get("open")),
                        "high": _float_val(item.get("high")),
                        "low": _float_val(item.get("low")),
                        "close": _float_val(item.get("close")),
                        "volume": _float_val(item.get("volume")),
                    }
                )
        return out

    def simulate_order(
        self,
        intent: OrderIntent,
        *,
        order_id_prefix: str = "mock",
    ) -> Dict[str, Any]:
        intent.validate()
        if self.open_positions >= MAX_OPEN_POSITIONS:
            raise SafetyCapViolation("open_positions_exceeds_cap")
        self.open_positions += 1
        oid = f"{order_id_prefix}-{hashlib.sha256(json.dumps(intent.__dict__, sort_keys=True).encode()).hexdigest()[:12]}"
        return {
            "order_id": oid,
            "symbol": intent.symbol.upper(),
            "side": intent.side.upper(),
            "qty": intent.qty,
            "price": intent.price,
            "stop_loss": intent.stop_loss,
            "max_hold_seconds": intent.max_hold_seconds,
            "leverage": intent.leverage,
            "margin_usd": intent.margin_usd,
            "category": intent.category,
            "mode": self.mode,
            "exchange_write": False,
        }

    def fetch_instrument_info(self, symbol: str = DEFAULT_SYMBOL) -> Dict[str, Any]:
        symbol = symbol.upper()
        params = {"category": DEFAULT_CATEGORY, "symbol": symbol}
        url = f"{self.base_url}/v5/market/instruments-info?{urlencode(params)}"
        self.urls_called.append(url)
        payload = _http_get_json(url)
        rows = ((payload.get("result") or {}).get("list") or [])
        if not rows:
            raise RuntimeError("empty_instrument_info")
        return rows[0]

    def set_leverage(self, leverage: int, symbol: str = DEFAULT_SYMBOL) -> Dict[str, Any]:
        if leverage > MAX_LEVERAGE:
            raise SafetyCapViolation("leverage_exceeds_cap")
        lev = str(leverage)
        body = {
            "category": DEFAULT_CATEGORY,
            "symbol": symbol.upper(),
            "buyLeverage": lev,
            "sellLeverage": lev,
        }
        try:
            return self._signed_post("/v5/position/set-leverage", body)
        except BybitDemoClientError as exc:
            if "110043" in str(exc):
                return {"retCode": 0, "retMsg": "leverage_not_modified_idempotent_ok"}
            raise

    def _qty_step_from_instrument(self, info: Dict[str, Any]) -> float:
        lot = (info.get("lotSizeFilter") or {})
        return _float_val(lot.get("qtyStep") or lot.get("minOrderQty") or 0.001)

    def _price_tick_from_instrument(self, info: Dict[str, Any]) -> float:
        price = (info.get("priceFilter") or {})
        return _float_val(price.get("tickSize") or 0.01)

    def place_demo_order(self, intent: OrderIntent) -> Dict[str, Any]:
        if self.mode in {"mock", "dry-run"}:
            raise BybitDemoClientError(f"place_demo_order_forbidden_in_{self.mode}")
        if self.mode != "demo-order":
            raise DemoOrderNotAllowedError("demo-order mode not enabled")
        intent.validate()
        if self.count_open_positions(intent.symbol, intent.category) > 0:
            raise SafetyCapViolation("open_positions_exceeds_cap")
        info = self.fetch_instrument_info(intent.symbol)
        qty_step = self._qty_step_from_instrument(info)
        tick = self._price_tick_from_instrument(info)
        side = "Buy" if intent.side.upper() in {"BUY", "LONG"} else "Sell"
        qty_str = _round_qty(intent.qty, qty_step)
        if _float_val(qty_str) <= 0:
            raise SafetyCapViolation("qty_too_small")
        self.set_leverage(min(intent.leverage, MAX_LEVERAGE), intent.symbol)
        body: Dict[str, Any] = {
            "category": intent.category,
            "symbol": intent.symbol.upper(),
            "side": side,
            "orderType": "Market",
            "qty": qty_str,
            "stopLoss": _round_price(intent.stop_loss, tick),
            "positionIdx": 0,
        }
        payload = self._signed_post("/v5/order/create", body)
        order_id = ((payload.get("result") or {}).get("orderId") or "")
        self.open_positions = 1
        return {
            "order_id": order_id,
            "symbol": intent.symbol.upper(),
            "side": side.upper(),
            "qty": qty_str,
            "price": intent.price,
            "stop_loss": intent.stop_loss,
            "stop_loss_attached": True,
            "max_hold_seconds": intent.max_hold_seconds,
            "leverage": intent.leverage,
            "margin_usd": intent.margin_usd,
            "category": intent.category,
            "mode": "demo-order",
            "demo_order_sent": True,
            "mainnet": False,
            "real_money": False,
            "exchange_write": True,
        }

    def close_demo_position_market(self, symbol: str = DEFAULT_SYMBOL) -> Dict[str, Any]:
        if self.mode != "demo-order":
            raise BybitDemoClientError("close_forbidden_outside_demo_order")
        positions = self.list_open_positions(symbol)
        if not positions:
            return {"closed": False, "reason": "no_open_position"}
        pos = positions[0]
        size = abs(_float_val(pos.get("size")))
        side_raw = str(pos.get("side") or "")
        close_side = "Sell" if side_raw.lower() == "buy" else "Buy"
        info = self.fetch_instrument_info(symbol)
        qty_str = _round_qty(size, self._qty_step_from_instrument(info))
        body = {
            "category": DEFAULT_CATEGORY,
            "symbol": symbol.upper(),
            "side": close_side,
            "orderType": "Market",
            "qty": qty_str,
            "reduceOnly": True,
            "positionIdx": 0,
        }
        payload = self._signed_post("/v5/order/create", body)
        order_id = ((payload.get("result") or {}).get("orderId") or "")
        self.open_positions = 0
        return {
            "closed": True,
            "order_id": order_id,
            "qty": qty_str,
            "side": close_side,
            "avg_entry": _float_val(pos.get("avgPrice")),
            "unrealised_pnl": _float_val(pos.get("unrealisedPnl")),
            "exit_reason": "force_close_or_manual",
        }

    def get_primary_open_position(self, symbol: str = DEFAULT_SYMBOL) -> Optional[Dict[str, Any]]:
        rows = self.list_open_positions(symbol)
        return rows[0] if rows else None

    def get_recent_closed_pnl(self, symbol: str = DEFAULT_SYMBOL) -> Optional[Dict[str, Any]]:
        params = {"category": DEFAULT_CATEGORY, "symbol": symbol.upper(), "limit": "1"}
        payload = self._signed_get("/v5/position/closed-pnl", params)
        rows = ((payload.get("result") or {}).get("list") or [])
        return rows[0] if rows else None

    def close_position(self) -> None:
        if self.open_positions > 0:
            self.open_positions -= 1

    @staticmethod
    def sign_request(payload: str, secret: str) -> str:
        return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def compute_max_allowed_margin(available_balance: float) -> float:
        return min(MAX_MARGIN_USD, max(0.0, available_balance) * SAFE_BALANCE_FRACTION)
