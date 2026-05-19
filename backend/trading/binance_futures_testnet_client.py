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
    "PEPE": "1000PEPEUSDT",
}


class BinanceTestnetError(RuntimeError):
    pass


class BinanceFuturesTestnetClient:
    BASE_URL = "https://demo-fapi.binance.com"
    WS_BASE_URL = "wss://fstream.binancefuture.com/ws"

    def __init__(self, api_key=None, api_secret=None, timeout=15):
        self.api_key = (api_key or os.getenv("BINANCE_FUTURES_TESTNET_API_KEY", "")).strip()
        self.api_secret = (api_secret or os.getenv("BINANCE_FUTURES_TESTNET_SECRET_KEY", "")).strip()
        self.timeout = timeout
        self._exchange_info = None
        self.base_url = os.getenv("BINANCE_FUTURES_BASE_URL", self.BASE_URL).strip().rstrip("/")
        self.ws_base_url = os.getenv("BINANCE_FUTURES_WS_BASE_URL", self.WS_BASE_URL).strip().rstrip("/")
        self.rate_limit_guard = BinanceRateLimitGuard()

    def is_configured(self):
        return bool(self.api_key and self.api_secret)

    def resolve_symbol(self, fleet):
        env_key = f"BINANCE_FUTURES_TESTNET_SYMBOL_{fleet.upper()}"
        return os.getenv(env_key, DEFAULT_FLEET_SYMBOLS.get(fleet, f"{fleet}USDT")).strip().upper()

    def get_server_time(self):
        return self._public_request("GET", "/fapi/v1/time").get("serverTime")

    def validate_credentials(self):
        data = self._signed_request("GET", "/fapi/v2/balance")
        if not isinstance(data, list):
            raise BinanceTestnetError("Unexpected Binance balance response")
        return data

    def get_balances(self):
        return self._signed_request("GET", "/fapi/v2/balance")

    def get_account_information(self):
        return self._signed_request("GET", "/fapi/v2/account")

    def get_all_position_risk(self):
        return self._signed_request("GET", "/fapi/v2/positionRisk")

    def get_open_orders(self, symbol=None):
        params = {"symbol": symbol} if symbol else None
        return self._signed_request("GET", "/fapi/v1/openOrders", params)

    def get_all_orders(self, symbol, limit=20):
        params = {"symbol": symbol, "limit": int(limit)}
        return self._signed_request("GET", "/fapi/v1/allOrders", params)

    def get_user_trades(self, symbol, limit=20):
        params = {"symbol": symbol, "limit": int(limit)}
        return self._signed_request("GET", "/fapi/v1/userTrades", params)

    def get_funding_rate_history(self, symbol, limit=20):
        params = {"symbol": symbol, "limit": int(limit)}
        return self._public_request("GET", "/fapi/v1/fundingRate", params)

    def get_order_book(self, symbol, limit=20):
        params = {"symbol": symbol, "limit": int(limit)}
        return self._public_request("GET", "/fapi/v1/depth", params)

    def get_book_ticker(self, symbol):
        return self._public_request("GET", "/fapi/v1/ticker/bookTicker", {"symbol": symbol})

    def get_premium_index(self, symbol):
        return self._public_request("GET", "/fapi/v1/premiumIndex", {"symbol": symbol})

    def get_open_interest(self, symbol):
        return self._public_request("GET", "/fapi/v1/openInterest", {"symbol": symbol})

    def create_listen_key(self):
        data = self._signed_request("POST", "/fapi/v1/listenKey", params={}, signed=False)
        return str(data.get("listenKey") or "")

    def keepalive_listen_key(self, listen_key):
        return self._signed_request("PUT", "/fapi/v1/listenKey", {"listenKey": listen_key}, signed=False)

    def close_listen_key(self, listen_key):
        return self._signed_request("DELETE", "/fapi/v1/listenKey", {"listenKey": listen_key}, signed=False)

    def build_user_stream_url(self, listen_key):
        return f"{self.ws_base_url}/{listen_key}"

    def get_exchange_info(self):
        if self._exchange_info is None:
            self._exchange_info = self._public_request("GET", "/fapi/v1/exchangeInfo")
        return self._exchange_info

    def get_symbol_info(self, symbol):
        info = self.get_exchange_info()
        for item in info.get("symbols", []):
            if item.get("symbol") == symbol:
                return item
        raise BinanceTestnetError(f"Symbol {symbol} not found on Binance Futures testnet")

    def get_symbol_leverage_bracket(self, symbol, estimated_notional=0.0):
        items = self._signed_request("GET", "/fapi/v1/leverageBracket", {"symbol": symbol})
        if isinstance(items, dict):
            items = [items]
        for item in items:
            if item.get("symbol") != symbol:
                continue
            brackets = item.get("brackets", []) or []
            if not brackets:
                break
            notional = float(estimated_notional or 0.0)
            chosen = brackets[-1]
            for bracket in brackets:
                floor = float(bracket.get("notionalFloor", 0.0) or 0.0)
                cap = float(bracket.get("notionalCap", 0.0) or 0.0)
                if floor <= notional <= cap or (cap == 0.0 and notional >= floor):
                    chosen = bracket
                    break
            return {
                "symbol": symbol,
                "initialLeverage": int(chosen.get("initialLeverage") or 1),
                "notionalFloor": float(chosen.get("notionalFloor", 0.0) or 0.0),
                "notionalCap": float(chosen.get("notionalCap", 0.0) or 0.0),
            }
        raise BinanceTestnetError(f"Leverage bracket for {symbol} not found")

    def normalize_quantity(self, symbol, quantity):
        symbol_info = self.get_symbol_info(symbol)
        market_filter = next((flt for flt in symbol_info.get("filters", []) if flt.get("filterType") == "MARKET_LOT_SIZE"), None)
        lot_filter = market_filter or next(
            (flt for flt in symbol_info.get("filters", []) if flt.get("filterType") == "LOT_SIZE"),
            None,
        )
        if not lot_filter:
            raise BinanceTestnetError(f"LOT_SIZE filter missing for {symbol}")

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

    def set_leverage(self, symbol, leverage):
        exchange_leverage = max(1, int(round(float(leverage))))
        return self._signed_request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": exchange_leverage})

    def set_margin_type_isolated(self, symbol):
        try:
            return self._signed_request("POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": "ISOLATED"})
        except BinanceTestnetError as exc:
            message = str(exc)
            if "-4046" in message or "No need to change margin type" in message:
                return {"symbol": symbol, "marginType": "ISOLATED", "unchanged": True}
            raise

    def place_market_order(self, symbol, side, quantity, reduce_only=False, client_order_id=None):
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": self._format_decimal(quantity),
            "reduceOnly": "true" if reduce_only else "false",
            "newOrderRespType": "RESULT",
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        return self._signed_request("POST", "/fapi/v1/order", params)

    def get_position_risk(self, symbol):
        positions = self._signed_request("GET", "/fapi/v2/positionRisk", {"symbol": symbol})
        if isinstance(positions, list):
            for item in positions:
                if item.get("symbol") == symbol:
                    return item
        raise BinanceTestnetError(f"Position risk for {symbol} not found")

    def extract_fill_price(self, order_payload, fallback_price):
        avg_price = float(order_payload.get("avgPrice") or 0.0)
        if avg_price > 0:
            return avg_price
        executed_qty = float(order_payload.get("executedQty") or 0.0)
        cum_quote = float(order_payload.get("cumQuote") or 0.0)
        if executed_qty > 0 and cum_quote > 0:
            return cum_quote / executed_qty
        return float(fallback_price)

    def _public_request(self, method, path, params=None):
        query = urlencode(params or {}, doseq=True)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        return self._send_request(method, url, headers={})

    def _signed_request(self, method, path, params=None, signed=True):
        if not self.is_configured():
            raise BinanceTestnetError("Binance futures testnet credentials are not configured")

        payload = dict(params or {})
        if signed:
            payload["timestamp"] = int(time.time() * 1000)
            payload["recvWindow"] = int(os.getenv("BINANCE_TESTNET_RECV_WINDOW", "5000"))
            query = urlencode(payload, doseq=True)
            signature = hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
            signed_query = f"{query}&signature={signature}"
        else:
            signed_query = urlencode(payload, doseq=True)
        url = f"{self.base_url}{path}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-MBX-APIKEY": self.api_key,
        }
        upper_method = method.upper()
        if upper_method in {"GET", "DELETE"}:
            url = f"{url}?{signed_query}"
            data = None
        else:
            data = signed_query.encode("utf-8")
        return self._send_request(method, url, headers=headers, data=data)

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
                    raise BinanceTestnetError("Binance futures testnet error 418: IP banned / retry blocked") from exc
                if exc.code == 429 and attempt < 4:
                    time.sleep(self.rate_limit_guard.register_retry(attempt))
                    last_exc = exc
                    continue
                try:
                    payload = json.loads(exc.read().decode("utf-8"))
                    code = payload.get("code", "ERR")
                    msg = payload.get("msg", str(exc))
                    raise BinanceTestnetError(f"Binance testnet error {code}: {msg}") from exc
                except BinanceTestnetError:
                    raise
                except Exception:
                    raise BinanceTestnetError(str(exc)) from exc
            except BinanceRateLimitError as exc:
                last_exc = exc
                time.sleep(self.rate_limit_guard.register_retry(attempt))
            except Exception as exc:
                raise BinanceTestnetError(str(exc)) from exc
        raise BinanceTestnetError(str(last_exc) if last_exc else "futures_request_failed")

    @staticmethod
    def _format_decimal(value):
        text = format(Decimal(str(value)).normalize(), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
