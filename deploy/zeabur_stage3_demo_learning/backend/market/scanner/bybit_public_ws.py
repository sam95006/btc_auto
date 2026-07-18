"""Bybit Mainnet public linear ticker WebSocket (Phase 4 Track B).

Public topics only · no API key · no private streams · research/scanner use.
"""
from __future__ import annotations

import json
import logging
import random
import ssl
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

WS_URL = "wss://stream.bybit.com/v5/public/linear"
_SUBSCRIBE_BATCH = 10
_PING_INTERVAL_SEC = 20.0
_MAX_SYMBOLS = 80

TickerCallback = Callable[[dict[str, Any]], None]
StatusCallback = Callable[[str], None]


def _f(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        n = float(v)
        return n if n == n else None  # NaN guard
    except (TypeError, ValueError):
        return None


def normalize_ticker_delta(msg: dict[str, Any], received_at: int | None = None) -> dict[str, Any] | None:
    """Normalize a Bybit tickers.* WS payload into scanner-shaped fields."""
    if not msg.get("topic") or not str(msg.get("topic")).startswith("tickers."):
        return None
    raw = msg.get("data")
    row = raw[0] if isinstance(raw, list) else raw
    if not isinstance(row, dict):
        return None
    symbol = str(row.get("symbol") or "").upper().strip()
    last = _f(row.get("lastPrice"))
    if not symbol or last is None:
        return None
    now = int(received_at if received_at is not None else time.time() * 1000)
    exch = _f(msg.get("ts")) or _f(row.get("ts"))
    exchange_ts = int(exch) if exch is not None else now
    pct = _f(row.get("price24hPcnt"))
    bid = _f(row.get("bid1Price"))
    ask = _f(row.get("ask1Price"))
    spread = None
    if bid is not None and ask is not None and last > 0 and ask >= bid:
        spread = ((ask - bid) / last) * 10_000.0
    return {
        "symbol": symbol,
        "lastPrice": last,
        "markPrice": _f(row.get("markPrice")),
        "indexPrice": _f(row.get("indexPrice")),
        "bid1": bid,
        "ask1": ask,
        "spreadBps": spread,
        "change24hPct": (pct * 100.0) if pct is not None else None,
        "openInterest": _f(row.get("openInterest")),
        "openInterestValue": _f(row.get("openInterestValue")),
        "fundingRate": _f(row.get("fundingRate")),
        "nextFundingTime": int(row["nextFundingTime"])
        if row.get("nextFundingTime") not in (None, "")
        else None,
        "volume24h": _f(row.get("volume24h")),
        "turnover24h": _f(row.get("turnover24h")),
        "exchangeTimestamp": exchange_ts,
        "receivedAt": now,
        "source": "BYBIT_MAINNET_LINEAR",
        "transport": "WS",
    }


class BybitPublicTickerWS:
    """Threaded public ticker socket with batch subscribe + reconnect backoff."""

    def __init__(
        self,
        *,
        on_ticker: TickerCallback | None = None,
        on_status: StatusCallback | None = None,
        url: str = WS_URL,
        max_symbols: int = _MAX_SYMBOLS,
    ) -> None:
        self._on_ticker = on_ticker
        self._on_status = on_status
        self._url = url
        self._max_symbols = max(1, min(int(max_symbols), _MAX_SYMBOLS))
        self._symbols: list[str] = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ws: Any = None
        self._connected = False
        self._attempt = 0
        self._reconnect_count = 0
        self._subscribed_topics = 0
        self._last_error = ""
        self._last_message_at = 0
        self._connection_count = 0
        self._ping_thread: threading.Thread | None = None

    def start(self, symbols: list[str]) -> None:
        syms = [s.upper().strip() for s in symbols if s][: self._max_symbols]
        with self._lock:
            self._symbols = syms
            if self._thread and self._thread.is_alive():
                # hot-replace subscription set on next reconnect cycle
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="nexus-bybit-public-ws",
                daemon=True,
            )
            self._thread.start()

    def update_symbols(self, symbols: list[str]) -> None:
        with self._lock:
            self._symbols = [s.upper().strip() for s in symbols if s][: self._max_symbols]

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=timeout)
        self._emit_status("closed")

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "wsConnected": self._connected,
                "wsReconnectCount": self._reconnect_count,
                "wsConnectionCount": self._connection_count,
                "subscribedTopics": self._subscribed_topics,
                "symbolCount": len(self._symbols),
                "lastMessageAt": self._last_message_at or None,
                "lastError": self._last_error or None,
                "url": self._url,
                "private_api": False,
                "api_key_used": False,
                "read_only": True,
            }

    def _emit_status(self, st: str) -> None:
        if self._on_status:
            try:
                self._on_status(st)
            except Exception as exc:  # noqa: BLE001
                logger.debug("ws status callback error: %s", exc)

    def _run_loop(self) -> None:
        try:
            import websocket  # websocket-client
        except ImportError:
            self._last_error = "websocket_client_unavailable"
            logger.warning("bybit_public_ws: websocket-client not installed; WS disabled")
            self._emit_status("error")
            return

        while not self._stop.is_set():
            self._emit_status("connecting" if self._attempt == 0 else "reconnecting")
            try:
                self._session(websocket)
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                logger.warning("bybit_public_ws session error: %s", exc)
            self._connected = False
            if self._stop.is_set():
                break
            self._attempt += 1
            self._reconnect_count += 1
            self._emit_status("reconnecting")
            delay = min(30.0, 0.8 * (2 ** min(self._attempt, 5))) + random.random() * 0.4
            self._stop.wait(delay)

    def _session(self, websocket: Any) -> None:
        opened = threading.Event()

        def on_open(ws: Any) -> None:
            with self._lock:
                self._connected = True
                self._attempt = 0
                self._connection_count += 1
                symbols = list(self._symbols)
            self._emit_status("open")
            opened.set()
            for i in range(0, len(symbols), _SUBSCRIBE_BATCH):
                batch = symbols[i : i + _SUBSCRIBE_BATCH]
                args = [f"tickers.{s}" for s in batch]
                try:
                    ws.send(json.dumps({"op": "subscribe", "args": args}))
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    break
            with self._lock:
                self._subscribed_topics = len(symbols)

        def on_message(_ws: Any, message: str) -> None:
            try:
                msg = json.loads(message)
            except (TypeError, ValueError, json.JSONDecodeError):
                return
            if msg.get("op") == "pong":
                return
            if msg.get("op") == "ping":
                try:
                    _ws.send(json.dumps({"op": "pong"}))
                except Exception:  # noqa: BLE001
                    pass
                return
            row = normalize_ticker_delta(msg)
            if not row:
                return
            with self._lock:
                self._last_message_at = int(time.time() * 1000)
            if self._on_ticker:
                try:
                    self._on_ticker(row)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("ws ticker callback error: %s", exc)

        def on_error(_ws: Any, err: Any) -> None:
            self._last_error = str(err)
            self._emit_status("error")

        def on_close(_ws: Any, *_args: Any) -> None:
            self._connected = False

        ws = websocket.WebSocketApp(
            self._url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self._ws = ws
        ping_stop = threading.Event()

        def ping_loop() -> None:
            while not self._stop.is_set() and not ping_stop.is_set():
                if self._connected:
                    try:
                        ws.send(json.dumps({"op": "ping"}))
                    except Exception:  # noqa: BLE001
                        pass
                ping_stop.wait(_PING_INTERVAL_SEC)

        pt = threading.Thread(target=ping_loop, name="nexus-bybit-ws-ping", daemon=True)
        self._ping_thread = pt
        pt.start()
        try:
            ws.run_forever(sslopt={"cert_reqs": ssl.CERT_REQUIRED}, ping_interval=0)
        finally:
            ping_stop.set()
            self._ws = None
            self._connected = False
