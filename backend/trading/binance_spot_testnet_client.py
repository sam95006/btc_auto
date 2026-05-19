import hashlib
import hmac
import json
import os
import time
from decimal import Decimal, ROUND_DOWN
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.trading.binance_rate_limit_guard import BinanceRateLimitError, BinanceRateLimitGuard

DEFAULT_FLEET_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "PEPE": "PEPEUSDT",
}


class BinanceSpotTestnetError(RuntimeError):
    pass


class BinanceSpotTestnetClient:
    DEFAULT_BASE_URL = "https://testnet.binance.vision/api"
    DEFAULT_WS_BASE_URL = "wss://stream.testnet.binance.vision/ws"

    def __init__(self, api_key=None, api_secret=None, timeout=15):
        self.api_key = (api_key or os.getenv("BINANCE_SPOT_TESTNET_API_KEY", "")).strip()
        self.api_secret = (api_secret or os.getenv("BINANCE_SPOT_TESTNET_SECRET_KEY", "")).strip()
        self.timeout = timeout
        self._exchange_info = None
        self.base_url = os.getenv("BINANCE_SPOT_BASE_URL", self.DEFAULT_BASE_URL).strip().rstrip("/")
        self.ws_base_url = os.getenv("BINANCE_SPOT_WS_BASE_URL", self.DEFAULT_WS_BASE_URL).strip().rstrip("/")
        self.rate_limit_guard = BinanceRateLimitGuard()

    def is_configured(self):
        return bool(self.api_key and self.api_secret)

    def resolve_symbol(self, fleet):
        env_key = f"BINANCE_SPOT_TESTNET_SYMBOL_{fleet.upper()}"
        return os.getenv(env_key, DEFAULT_FLEET_SYMBOLS.get(fleet, f"{fleet}USDT")).strip().upper()

    def validate_credentials(self):
        data = self._signed_request("GET", "/v3/account")
        if not isinstance(data, dict):
            raise BinanceSpotTestnetError("Unexpected Binance spot account response")
        return data

    def get_account(self):
        return self._signed_request("GET", "/v3/account")

    def get_open_orders(self, symbol=None):
        params = {"symbol": symbol} if symbol else None
        return self._signed_request("GET", "/v3/openOrders", params)

    def get_my_trades(self, symbol, limit=50):
        return self._signed_request("GET", "/v3/myTrades", {"symbol": symbol, "limit": int(limit)})

    def get_book_ticker(self, symbol):
        return self._public_request("GET", "/v3/ticker/bookTicker", {"symbol": symbol})

    def get_order_book(self, symbol, limit=20):
        return self._public_request("GET", "/v3/depth", {"symbol": symbol, "limit": int(limit)})

    def create_listen_key(self):
        data = self._signed_request("POST", "/v3/userDataStream", params={}, signed=False)
        return str(data.get("listenKey") or "")

    def keepalive_listen_key(self, listen_key):
        return self._signed_request("PUT", "/v3/userDataStream", {"listenKey": listen_key}, signed=False)

    def close_listen_key(self, listen_key):
        return self._signed_request("DELETE", "/v3/userDataStream", {"listenKey": listen_key}, signed=False)

    def build_user_stream_url(self, listen_key):
        return f"{self.ws_base_url}/{listen_key}"

    def get_exchange_info(self):
        if self._exchange_info is None:
            self._exchange_info = self._public_request("GET", "/v3/exchangeInfo")
        return self._exchange_info

    def get_symbol_info(self, symbol):
        info = self.get_exchange_info()
        for item in info.get("symbols", []):
            if item.get("symbol") == symbol:
                return item
        raise BinanceSpotTestnetError(f"Symbol {symbol} not found on Binance Spot testnet")

    def normalize_quantity(self, symbol, quantity):
        symbol_info = self.get_symbol_info(symbol)
        lot_filter = next((flt for flt in symbol_info.get("filters", []) if flt.get("filterType") == "LOT_SIZE"), None)
        if not lot_filter:
            raise BinanceSpotTestnetError(f"LOT_SIZE filter missing for {symbol}")

        step_size = Decimal(str(lot_filter.get("stepSize", "1")))
        min_qty = Decimal(str(lot_filter.get("minQty", "0")))
        max_qty = Decimal(str(lot_filter.get("maxQty", "999999999")))
        requested = Decimal(str(quantity))

        normalized = requested.quantize(step_size, rounding=ROUND_DOWN)
        if step_size > 0:
            normalized = (normalized // step_size) * step_size
        if normalized < min_qty:
            normalized = min_qty
        if normalized > max_qty:
            normalized = max_qty
        return float(normalized.normalize())

    def place_market_buy(self, symbol, quote_order_qty, client_order_id=None):
        params = {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": self._format_decimal(quote_order_qty),
            "newOrderRespType": "FULL",
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        return self._signed_request("POST", "/v3/order", params)

    def place_market_sell(self, symbol, quantity, client_order_id=None):
        params = {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": self._format_decimal(quantity),
            "newOrderRespType": "FULL",
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        return self._signed_request("POST", "/v3/order", params)

    def extract_fill_price(self, order_payload, fallback_price):
        fills = order_payload.get("fills") or []
        if fills:
            total_qty = sum(float(item.get("qty") or 0.0) for item in fills)
            total_quote = sum(float(item.get("qty") or 0.0) * float(item.get("price") or 0.0) for item in fills)
            if total_qty > 0 and total_quote > 0:
                return total_quote / total_qty
        executed_qty = float(order_payload.get("executedQty") or 0.0)
        cummulative_quote_qty = float(order_payload.get("cummulativeQuoteQty") or 0.0)
        if executed_qty > 0 and cummulative_quote_qty > 0:
            return cummulative_quote_qty / executed_qty
        return float(fallback_price)

    def _public_request(self, method, path, params=None):
        query = urlencode(params or {}, doseq=True)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        return self._send_request(method, url, headers={})

    def _signed_request(self, method, path, params=None, signed=True):
        if not self.is_configured():
            raise BinanceSpotTestnetError("Binance spot testnet credentials are not configured")

        payload = dict(params or {})
        if signed:
            payload["timestamp"] = int(time.time() * 1000)
            payload["recvWindow"] = int(os.getenv("BINANCE_TESTNET_RECV_WINDOW", "5000"))
            query = urlencode(payload, doseq=True)
            signature = hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
            payload["signature"] = signature
        url = f"{self.base_url}{path}?{urlencode(payload, doseq=True)}" if payload else f"{self.base_url}{path}"
        headers = {"X-MBX-APIKEY": self.api_key}
        return self._send_request(method, url, headers=headers)

    def _send_request(self, method, url, headers=None, data=None):
        last_exc = None
        for attempt in range(1, 4):
            self.rate_limit_guard.before_request()
            request = Request(url, data=data, headers=headers or {}, method=method)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    self.rate_limit_guard.after_response(response.status, dict(response.headers.items()))
                    payload = json.loads(response.read().decode("utf-8"))
                    return payload
            except HTTPError as exc:
                self.rate_limit_guard.after_response(exc.code, dict(exc.headers.items()) if exc.headers else {})
                if exc.code == 418:
                    raise BinanceSpotTestnetError("Binance spot testnet error 418: IP banned / retry blocked") from exc
                if exc.code == 429 and attempt < 4:
                    time.sleep(self.rate_limit_guard.register_retry(attempt))
                    last_exc = exc
                    continue
                try:
                    payload = json.loads(exc.read().decode("utf-8"))
                    code = payload.get("code", "ERR")
                    msg = payload.get("msg", str(exc))
                    raise BinanceSpotTestnetError(f"Binance spot testnet error {code}: {msg}") from exc
                except BinanceSpotTestnetError:
                    raise
                except Exception:
                    raise BinanceSpotTestnetError(str(exc)) from exc
            except BinanceRateLimitError as exc:
                last_exc = exc
                time.sleep(self.rate_limit_guard.register_retry(attempt))
            except Exception as exc:
                raise BinanceSpotTestnetError(str(exc)) from exc
        raise BinanceSpotTestnetError(str(last_exc) if last_exc else "spot_request_failed")

    @staticmethod
    def _format_decimal(value):
        text = format(Decimal(str(value)).normalize(), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
