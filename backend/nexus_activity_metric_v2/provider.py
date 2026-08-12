"""OfficialTradeActivityProvider — Bybit public trades REST + WS stubs.

Works against real public endpoints (read-only). No exchange writes.
WS interface is a stub that accepts/normalizes publicTrade payloads.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from backend.nexus_activity_metric_v2.constants import (
    BYBIT_PUBLIC_TRADE_TOPIC_PREFIX,
    BYBIT_PUBLIC_WS_URL,
    BYBIT_RECENT_TRADE_PATH,
    BYBIT_REST_BASE,
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RATE_LIMIT_PER_SECOND,
    DEFAULT_TIMEOUT_SECONDS,
    SOURCE_REST,
    SOURCE_WS,
)
from backend.nexus_activity_metric_v2.models import TradeEvent


@dataclass
class RateLimitState:
    rate_per_second: float = DEFAULT_RATE_LIMIT_PER_SECOND
    tokens: float = field(init=False)
    updated_at: float = field(init=False)
    wait_count: int = 0
    hit_count: int = 0

    def __post_init__(self) -> None:
        self.tokens = float(self.rate_per_second)
        self.updated_at = time.monotonic()

    def acquire(self) -> None:
        while True:
            now = time.monotonic()
            elapsed = now - self.updated_at
            self.updated_at = now
            self.tokens = min(
                self.rate_per_second, self.tokens + elapsed * self.rate_per_second
            )
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            self.wait_count += 1
            self.hit_count += 1
            time.sleep(max(0.01, (1.0 - self.tokens) / self.rate_per_second))


HttpGetter = Callable[[str, dict[str, Any]], dict[str, Any]]


def _default_http_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    full = f"{url}?{qs}" if qs else url
    req = urllib.request.Request(
        full,
        headers={"User-Agent": "NEXUS-activity-metric-v2/readonly"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


@dataclass
class OfficialTradeActivityProvider:
    """Read-only provider for Bybit linear public trades."""

    base_url: str = BYBIT_REST_BASE
    category: str = "linear"
    http_get: HttpGetter = field(default=_default_http_get)
    rate_limiter: RateLimitState = field(default_factory=RateLimitState)
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS
    available: bool = True
    degraded: bool = False
    last_error: str | None = None
    request_count: int = 0
    rate_limit_response_count: int = 0

    # --- REST -----------------------------------------------------------------

    def fetch_recent_trades(
        self, *, symbol: str, limit: int = 1000
    ) -> list[TradeEvent]:
        """GET /v5/market/recent-trade — public, no auth."""
        receive_ms = int(time.time() * 1000)
        payload = self._get_with_retry(
            BYBIT_RECENT_TRADE_PATH,
            {"category": self.category, "symbol": symbol, "limit": int(limit)},
        )
        rows = (payload.get("result") or {}).get("list") or []
        events: list[TradeEvent] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ev = self.normalize_rest_row(row, symbol=symbol, receive_time_ms=receive_ms)
            if ev is not None:
                events.append(ev)
        return events

    def normalize_rest_row(
        self, row: dict[str, Any], *, symbol: str, receive_time_ms: int
    ) -> TradeEvent | None:
        trade_id = row.get("execId") or row.get("id") or row.get("tradeId")
        if trade_id is None:
            return None
        price = _f(row.get("price"))
        size = _f(row.get("size") or row.get("qty"))
        if price is None or size is None:
            return None
        time_raw = row.get("time") or row.get("T") or row.get("timestamp")
        try:
            event_time_ms = int(time_raw)
        except (TypeError, ValueError):
            return None
        return TradeEvent(
            trade_id=str(trade_id),
            symbol=str(row.get("symbol") or symbol),
            price=float(price),
            size=float(size),
            side=str(row.get("side") or ""),
            event_time_ms=event_time_ms,
            receive_time_ms=int(receive_time_ms),
            source=SOURCE_REST,
            notional=float(price) * float(size),
        )

    # --- WS stubs -------------------------------------------------------------

    @property
    def ws_url(self) -> str:
        return BYBIT_PUBLIC_WS_URL

    def ws_subscribe_args(self, symbols: list[str]) -> dict[str, Any]:
        """Build Bybit public WS subscribe frame for publicTrade topics."""
        args = [f"{BYBIT_PUBLIC_TRADE_TOPIC_PREFIX}.{s}" for s in symbols]
        return {"op": "subscribe", "args": args}

    def normalize_ws_message(
        self, message: dict[str, Any], *, receive_time_ms: int | None = None
    ) -> Iterator[TradeEvent]:
        """Normalize a publicTrade WS payload into TradeEvents (stub consumer)."""
        recv = receive_time_ms if receive_time_ms is not None else int(time.time() * 1000)
        topic = str(message.get("topic") or "")
        if not topic.startswith(BYBIT_PUBLIC_TRADE_TOPIC_PREFIX):
            return
            yield  # pragma: no cover — makes this a generator
        data = message.get("data") or []
        if isinstance(data, dict):
            data = [data]
        symbol_from_topic = topic.split(".", 1)[-1] if "." in topic else ""
        for row in data:
            if not isinstance(row, dict):
                continue
            trade_id = row.get("i") or row.get("execId") or row.get("id")
            price = _f(row.get("p") or row.get("price"))
            size = _f(row.get("v") or row.get("size"))
            if trade_id is None or price is None or size is None:
                continue
            time_raw = row.get("T") or row.get("time")
            try:
                event_time_ms = int(time_raw)
            except (TypeError, ValueError):
                continue
            side_raw = row.get("S") or row.get("side") or ""
            yield TradeEvent(
                trade_id=str(trade_id),
                symbol=str(row.get("s") or row.get("symbol") or symbol_from_topic),
                price=float(price),
                size=float(size),
                side=str(side_raw),
                event_time_ms=event_time_ms,
                receive_time_ms=int(recv),
                source=SOURCE_WS,
                notional=float(price) * float(size),
            )

    def ws_connect_stub(self) -> dict[str, Any]:
        """Interface stub — does not open a live socket in unit tests."""
        return {
            "url": self.ws_url,
            "connected": False,
            "stub": True,
            "topics_supported": [f"{BYBIT_PUBLIC_TRADE_TOPIC_PREFIX}.{{symbol}}"],
            "note": "Live WS connect is opt-in; stub validates contract only.",
        }

    # --- transport ------------------------------------------------------------

    def _get_with_retry(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + path
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.rate_limiter.acquire()
            self.request_count += 1
            try:
                payload = self.http_get(url, params)
                ret = payload.get("retCode")
                if ret == 10006 or ret == 10018:  # rate limit / too many visits
                    self.rate_limit_response_count += 1
                    self.degraded = True
                    time.sleep(self.backoff_base_seconds * (2**attempt))
                    continue
                if ret not in (0, None):
                    self.last_error = f"retCode={ret}:{payload.get('retMsg')}"
                    self.degraded = True
                return payload
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code == 429:
                    self.rate_limit_response_count += 1
                    self.degraded = True
                time.sleep(self.backoff_base_seconds * (2**attempt))
            except Exception as exc:  # noqa: BLE001 — bounded retry
                last_exc = exc
                time.sleep(self.backoff_base_seconds * (2**attempt))
        self.available = False
        self.last_error = str(last_exc) if last_exc else "unknown_http_failure"
        return {"retCode": -1, "retMsg": self.last_error, "result": {"list": []}}


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
