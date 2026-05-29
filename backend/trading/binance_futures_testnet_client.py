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


def _clean_credential(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text.replace("\ufeff", "").replace("\r", "").replace("\n", "")


def _resolve_futures_testnet_secret(explicit=None) -> str:
    if explicit:
        return _clean_credential(explicit)
    for env_key in (
        "BINANCE_FUTURES_TESTNET_SECRET_KEY",
        "BINANCE_FUTURES_TESTNET_API_SECRET",
        "BINANCE_FUTURES_TESTNET_SECRET",
    ):
        value = _clean_credential(os.getenv(env_key, ""))
        if value:
            return value
    return ""


class BinanceFuturesTestnetClient:
    BASE_URL = "https://demo-fapi.binance.com"
    WS_BASE_URL = "wss://fstream.binancefuture.com/ws"

    def __init__(self, api_key=None, api_secret=None, timeout=15):
        self.api_key = _clean_credential(api_key or os.getenv("BINANCE_FUTURES_TESTNET_API_KEY", ""))
        self.api_secret = _resolve_futures_testnet_secret(api_secret)
        self.timeout = timeout
        self._exchange_info = None
        self._dual_side_position = None
        self._tradable_symbols = None
        self._time_offset_ms = None
        self.base_url = _clean_credential(os.getenv("BINANCE_FUTURES_BASE_URL", self.BASE_URL)).rstrip("/")
        self.ws_base_url = _clean_credential(os.getenv("BINANCE_FUTURES_WS_BASE_URL", self.WS_BASE_URL)).rstrip("/")
        self.rate_limit_guard = BinanceRateLimitGuard()

    def is_configured(self):
        return bool(self.api_key and self.api_secret)

    def api_key_fingerprint(self):
        if not self.api_key:
            return ""
        return hashlib.sha256(self.api_key.encode("utf-8")).hexdigest()[:12]

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

    def get_income_history(self, symbol=None, income_type=None, limit=50):
        params = {"limit": int(limit)}
        if symbol:
            params["symbol"] = str(symbol).upper()
        if income_type:
            params["incomeType"] = str(income_type)
        return self._signed_request("GET", "/fapi/v1/income", params)

    def get_funding_rate_history(self, symbol, limit=20):
        params = {"symbol": symbol, "limit": int(limit)}
        return self._public_request("GET", "/fapi/v1/fundingRate", params)

    def get_order_book(self, symbol, limit=20):
        params = {"symbol": symbol, "limit": int(limit)}
        return self._public_request("GET", "/fapi/v1/depth", params)

    def get_book_ticker(self, symbol):
        return self._public_request("GET", "/fapi/v1/ticker/bookTicker", {"symbol": symbol})

    def fetch_24h_tickers(self):
        data = self._public_request("GET", "/fapi/v1/ticker/24hr")
        return data if isinstance(data, list) else []

    def get_premium_index(self, symbol):
        return self._public_request("GET", "/fapi/v1/premiumIndex", {"symbol": symbol})

    def get_open_interest(self, symbol):
        return self._public_request("GET", "/fapi/v1/openInterest", {"symbol": symbol})

    def get_klines(self, symbol, interval="5m", limit=100):
        params = {
            "symbol": str(symbol).upper(),
            "interval": str(interval),
            "limit": int(limit),
        }
        data = self._public_request("GET", "/fapi/v1/klines", params)
        return data if isinstance(data, list) else []

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

    def tradable_symbols(self):
        if self._tradable_symbols is None:
            info = self.get_exchange_info()
            self._tradable_symbols = {
                str(item.get("symbol") or "").upper()
                for item in info.get("symbols", [])
                if item.get("status") == "TRADING" and item.get("contractType") == "PERPETUAL"
            }
        return set(self._tradable_symbols)

    def is_tradable_symbol(self, symbol):
        symbol = str(symbol or "").upper()
        if not symbol:
            return False
        return symbol in self.tradable_symbols()

    def filter_tradable_symbols(self, symbols):
        tradable = self.tradable_symbols()
        return [str(item).upper() for item in (symbols or []) if str(item).upper() in tradable]

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

    def place_market_order(
        self,
        symbol,
        side,
        quantity,
        reduce_only=False,
        client_order_id=None,
        position_side=None,
        omit_position_side=False,
        use_result_resp=True,
    ):
        params = {
            "symbol": str(symbol).upper(),
            "side": str(side).upper(),
            "type": "MARKET",
            "quantity": self._format_decimal(quantity),
            "reduceOnly": "true" if reduce_only else "false",
        }
        if use_result_resp:
            params["newOrderRespType"] = "RESULT"
        if not omit_position_side:
            ps = str(position_side or "").upper()
            if ps:
                params["positionSide"] = ps
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        return self._signed_request("POST", "/fapi/v1/order", params)

    def place_limit_order(
        self,
        symbol,
        side,
        quantity,
        price,
        *,
        reduce_only=False,
        client_order_id=None,
        position_side=None,
        omit_position_side=False,
        time_in_force="GTC",
    ):
        params = {
            "symbol": str(symbol).upper(),
            "side": str(side).upper(),
            "type": "LIMIT",
            "quantity": self._format_decimal(quantity),
            "price": self._format_decimal(price),
            "timeInForce": str(time_in_force or "GTC").upper(),
            "reduceOnly": "true" if reduce_only else "false",
        }
        if not omit_position_side:
            ps = str(position_side or "").upper()
            if ps:
                params["positionSide"] = ps
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        return self._signed_request("POST", "/fapi/v1/order", params)

    def test_market_order(self, symbol, side, quantity, reduce_only=False, position_side=None, omit_position_side=False):
        params = {
            "symbol": str(symbol).upper(),
            "side": str(side).upper(),
            "type": "MARKET",
            "quantity": self._format_decimal(quantity),
            "reduceOnly": "true" if reduce_only else "false",
        }
        if not omit_position_side:
            ps = str(position_side or "").upper()
            if ps:
                params["positionSide"] = ps
        return self._signed_request("POST", "/fapi/v1/order/test", params)

    def get_dual_side_position(self):
        if self._dual_side_position is not None:
            return self._dual_side_position
        data = self._signed_request("GET", "/fapi/v1/positionSide/dual")
        self._dual_side_position = bool(data.get("dualSidePosition"))
        return self._dual_side_position

    def fetch_open_position(self, symbol):
        symbol = str(symbol or "").upper()
        for item in self.get_all_position_risk():
            if str(item.get("symbol") or "").upper() != symbol:
                continue
            position_amt = float(item.get("positionAmt", 0.0) or 0.0)
            if abs(position_amt) < 1e-12:
                continue
            return {
                "symbol": symbol,
                "position_amt": position_amt,
                "position_side": str(item.get("positionSide") or "BOTH").upper(),
                "entry_price": float(item.get("entryPrice", 0.0) or 0.0),
                "mark_price": float(item.get("markPrice", 0.0) or 0.0),
                "quantity": abs(position_amt),
            }
        return None

    def close_open_position_market(self, symbol, client_order_id=None):
        """Close an open futures position using live positionRisk and hedge/one-way retries."""
        live = self.fetch_open_position(symbol)
        if not live:
            raise BinanceTestnetError(f"No open position for {symbol}")

        position_amt = float(live["position_amt"])
        quantity = self.normalize_quantity(symbol, abs(position_amt))
        if quantity <= 0:
            raise BinanceTestnetError(f"{symbol} close quantity is zero after normalization")

        close_side = "SELL" if position_amt > 0 else "BUY"
        exchange_ps = str(live.get("position_side") or "BOTH").upper()
        hedge_mode = self.get_dual_side_position()

        attempts = []
        if hedge_mode:
            hedge_ps = exchange_ps if exchange_ps in {"LONG", "SHORT"} else ("LONG" if position_amt > 0 else "SHORT")
            attempts.append({"position_side": hedge_ps, "omit_position_side": False, "reduce_only": True, "result_resp": False})
            alt_ps = "SHORT" if hedge_ps == "LONG" else "LONG"
            attempts.append({"position_side": alt_ps, "omit_position_side": False, "reduce_only": True, "result_resp": False})
        else:
            attempts.append({"position_side": "BOTH", "omit_position_side": False, "reduce_only": True, "result_resp": False})
            attempts.append({"position_side": None, "omit_position_side": True, "reduce_only": True, "result_resp": False})
            attempts.append({"position_side": "BOTH", "omit_position_side": False, "reduce_only": False, "result_resp": False})
            attempts.append({"position_side": None, "omit_position_side": True, "reduce_only": False, "result_resp": False})

        last_exc = None
        for index, attempt in enumerate(attempts):
            order_id = client_order_id
            if order_id and index > 0:
                order_id = f"{order_id[:20]}_{index}"
            try:
                return self.place_market_order(
                    symbol=symbol,
                    side=close_side,
                    quantity=quantity,
                    reduce_only=bool(attempt.get("reduce_only", True)),
                    client_order_id=order_id,
                    position_side=attempt.get("position_side"),
                    omit_position_side=bool(attempt.get("omit_position_side")),
                    use_result_resp=bool(attempt.get("result_resp", False)),
                )
            except BinanceTestnetError as exc:
                last_exc = exc
                message = str(exc)
                if "-1109" not in message and "-4061" not in message and "-2019" not in message and "-4164" not in message:
                    raise
        raise last_exc or BinanceTestnetError(f"Unable to close {symbol}")

    def validate_trading_access(self, symbol="ETHUSDT"):
        result = {
            "configured": self.is_configured(),
            "base_url": self.base_url,
            "api_key_fingerprint": self.api_key_fingerprint(),
            "symbol": str(symbol).upper(),
        }
        if not self.is_configured():
            result["ok"] = False
            result["error"] = "credentials_missing"
            return result
        try:
            account = self.get_account_information()
            result["can_trade"] = bool(account.get("canTrade", True))
            result["can_deposit"] = bool(account.get("canDeposit", True))
            result["dual_side_position"] = self.get_dual_side_position()
            live = self.fetch_open_position(symbol)
            result["has_open_position"] = bool(live)
            if live:
                result["live_position_side"] = live.get("position_side")
                result["live_position_amt"] = live.get("position_amt")
        except BinanceTestnetError as exc:
            result["ok"] = False
            result["read_error"] = str(exc)
            return result

        write_probe = self.probe_write_access(symbol)
        result["write_probe"] = write_probe
        result["write_post_probe"] = self.probe_write_post_access(symbol)
        try:
            if live:
                close_side = "SELL" if float(live["position_amt"]) > 0 else "BUY"
                qty = self.normalize_quantity(symbol, abs(float(live["position_amt"])))
                hedge_mode = bool(result.get("dual_side_position"))
                test_kwargs = {
                    "symbol": symbol,
                    "side": close_side,
                    "quantity": qty,
                    "reduce_only": True,
                }
                if hedge_mode:
                    test_kwargs["position_side"] = live.get("position_side")
                else:
                    test_kwargs["position_side"] = "BOTH"
                    test_kwargs["omit_position_side"] = False
                self.test_market_order(**test_kwargs)
                result["order_test"] = {"ok": True}
            else:
                result["order_test"] = {"ok": True, "skipped": "no_open_position"}
        except BinanceTestnetError as exc:
            result["order_test"] = {"ok": False, "error": str(exc)}

        result["ok"] = bool(result.get("can_trade", True)) and bool(write_probe.get("ok"))
        post_probe = result.get("write_post_probe") or {}
        if post_probe.get("ok") is False:
            result["ok"] = False
        if result.get("order_test") and result["order_test"].get("ok") is False:
            result["ok"] = False
        return result

    def probe_write_post_access(self, symbol="ETHUSDT"):
        """Real signed POST probe. order/test alone is not sufficient on Binance Demo."""
        symbol = str(symbol or "ETHUSDT").upper()
        try:
            self.set_margin_type_isolated(symbol)
            return {
                "ok": True,
                "probe": "marginType_post",
                "symbol": symbol,
                "note": "signed POST accepted",
            }
        except BinanceTestnetError as exc:
            message = str(exc)
            hint = ""
            if "-1109" in message:
                hint = (
                    "Binance Demo rejected all signed POST trade calls. "
                    "Recreate API key on demo.binance.com with Futures permission enabled."
                )
            return {
                "ok": False,
                "probe": "marginType_post",
                "symbol": symbol,
                "error": message,
                "hint": hint,
            }

    def probe_write_access(self, symbol="ETHUSDT"):
        """Connectivity probe: account trade flag + position mode (no orders placed)."""
        try:
            account = self.get_account_information()
            can_trade = bool(account.get("canTrade", True))
            dual = self.get_dual_side_position()
            return {
                "ok": can_trade,
                "probe": "account_can_trade",
                "symbol": str(symbol).upper(),
                "can_trade": can_trade,
                "dual_side_position": dual,
                "api_key_fingerprint": self.api_key_fingerprint(),
                "base_url": self.base_url,
            }
        except BinanceTestnetError as exc:
            return {
                "ok": False,
                "probe": "account_can_trade",
                "symbol": str(symbol).upper(),
                "error": str(exc),
                "api_key_fingerprint": self.api_key_fingerprint(),
                "base_url": self.base_url,
            }

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

    def _ensure_time_offset(self):
        if self._time_offset_ms is not None:
            return
        try:
            server = int(self.get_server_time())
            self._time_offset_ms = server - int(time.time() * 1000)
        except Exception:
            self._time_offset_ms = 0

    def _timestamp_ms(self):
        self._ensure_time_offset()
        return int(time.time() * 1000) + int(self._time_offset_ms or 0)

    def _signed_request(self, method, path, params=None, signed=True):
        if not self.is_configured():
            raise BinanceTestnetError("Binance futures testnet credentials are not configured")

        payload = dict(params or {})
        if signed:
            payload["timestamp"] = self._timestamp_ms()
            payload["recvWindow"] = int(os.getenv("BINANCE_TESTNET_RECV_WINDOW", "10000"))
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
