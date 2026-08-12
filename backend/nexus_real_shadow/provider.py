"""Bybit public HTTP client — GET market data only, injectable transport."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from backend.nexus_real_shadow.constitution import PublicMarketDataConstitution, PublicDataBoundaryError
from backend.nexus_real_shadow.http_client import CircuitBreakerState, PublicHttpClient
from backend.nexus_real_shadow.instruments import load_fixture, parse_instruments_info
from backend.nexus_real_shadow.market_data import (
    parse_funding_payload,
    parse_kline_rows,
    parse_open_interest_payload,
    parse_orderbook_payload,
    parse_tickers_payload,
)

TransportFn = Callable[..., dict[str, Any]]

BYBIT_PUBLIC_BASE = "https://api.bybit.com"


@dataclass
class BybitPublicHttpClient:
    """Public market data client — never sends auth headers."""

    constitution: PublicMarketDataConstitution = field(default_factory=PublicMarketDataConstitution)
    http: PublicHttpClient | None = None
    base_url: str = BYBIT_PUBLIC_BASE
    use_fixtures: bool = False

    def __post_init__(self) -> None:
        if self.http is None:
            self.http = PublicHttpClient(constitution=self.constitution)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        if self.use_fixtures:
            return self._fixture_for_path(path, params)
        return self.http.get(url, params=params or {})

    def _fixture_for_path(self, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        params = params or {}
        if path == "/v5/market/instruments-info":
            return {"ok": True, "json": load_fixture("instruments_info.json")}
        if path == "/v5/market/tickers":
            return {"ok": True, "json": load_fixture("tickers.json")}
        if path == "/v5/market/orderbook":
            return {"ok": True, "json": load_fixture("orderbook.json")}
        if path == "/v5/market/funding/history":
            return {"ok": True, "json": load_fixture("funding.json")}
        if path == "/v5/market/open-interest":
            return {"ok": True, "json": load_fixture("open_interest.json")}
        if path == "/v5/market/kline":
            return {"ok": True, "json": load_fixture("kline.json")}
        return {"ok": False, "error": f"no_fixture_for:{path}", "params": params}

    def fetch_instruments_info(self, *, category: str = "linear") -> list[dict[str, Any]]:
        raw = self._get("/v5/market/instruments-info", {"category": category})
        payload = raw.get("json") or raw
        return parse_instruments_info(payload)

    def fetch_tickers(self, *, category: str = "linear", symbol: str | None = None) -> dict[str, dict[str, Any]]:
        params: dict[str, Any] = {"category": category}
        if symbol:
            params["symbol"] = symbol
        raw = self._get("/v5/market/tickers", params)
        payload = raw.get("json") or raw
        return parse_tickers_payload(payload)

    def fetch_klines(
        self,
        *,
        category: str = "linear",
        symbol: str,
        interval: str = "5",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        raw = self._get(
            "/v5/market/kline",
            {"category": category, "symbol": symbol, "interval": interval, "limit": limit},
        )
        payload = raw.get("json") or raw
        rows = (payload.get("result") or {}).get("list") or []
        return parse_kline_rows(rows)

    def fetch_orderbook(self, *, category: str = "linear", symbol: str, limit: int = 50) -> dict[str, Any]:
        raw = self._get("/v5/market/orderbook", {"category": category, "symbol": symbol, "limit": limit})
        payload = raw.get("json") or raw
        return parse_orderbook_payload(payload, symbol)

    def fetch_funding_history(self, *, category: str = "linear", symbol: str | None = None) -> dict[str, float | None]:
        params: dict[str, Any] = {"category": category, "limit": 1}
        if symbol:
            params["symbol"] = symbol
        raw = self._get("/v5/market/funding/history", params)
        payload = raw.get("json") or raw
        return parse_funding_payload(payload)

    def fetch_open_interest(self, *, category: str = "linear", symbol: str | None = None) -> dict[str, float | None]:
        params: dict[str, Any] = {"category": category, "intervalTime": "5min", "limit": 1}
        if symbol:
            params["symbol"] = symbol
        raw = self._get("/v5/market/open-interest", params)
        payload = raw.get("json") or raw
        return parse_open_interest_payload(payload)

    def stats(self) -> dict[str, Any]:
        return self.http.stats() if self.http else {}


__all__ = [
    "BybitPublicHttpClient",
    "BYBIT_PUBLIC_BASE",
    "PublicDataBoundaryError",
    "CircuitBreakerState",
]
