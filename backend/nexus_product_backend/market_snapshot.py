"""Credential-free public market snapshot for the staging product API.

This module accepts only the official read-only market adapter. It has no
account, order, position, or execution capability.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from backend.nexus_official_market_adapters.binance.adapter import BinanceUsdmPublicAdapter
from backend.nexus_official_market_adapters.constants import DATA_MODE_LIVE_READ_ONLY

SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "TRXUSDT", "LTCUSDT",
    "BCHUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
    "TONUSDT", "INJUSDT", "ATOMUSDT", "ETCUSDT", "FILUSDT", "AAVEUSDT",
    "MKRUSDT", "UNIUSDT", "PEPEUSDT", "WIFUSDT", "SEIUSDT", "TIAUSDT",
)
POLL_INTERVAL_SEC = 8.0
HISTORY_INTERVALS = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})
HISTORY_LIMIT_MIN = 10
HISTORY_LIMIT_MAX = 120


def _utc_from_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PublicMarketSnapshotService:
    """Small bounded cache with honest stale fallback."""

    def __init__(
        self,
        *,
        adapter: BinanceUsdmPublicAdapter | None = None,
        clock: Callable[[], float] = time.monotonic,
        cache_ttl_sec: float = POLL_INTERVAL_SEC,
    ) -> None:
        self.adapter = adapter or BinanceUsdmPublicAdapter(use_fixtures=False)
        self.clock = clock
        self.cache_ttl_sec = cache_ttl_sec
        self._cache: dict[str, Any] | None = None
        self._cached_at = 0.0

    def snapshot(self) -> tuple[dict[str, Any], int]:
        if self._cache is not None and self.clock() - self._cached_at < self.cache_ttl_sec:
            return self._cache, 200

        rows: list[dict[str, Any]] = []
        failures = 0
        for symbol in SYMBOLS:
            try:
                observation = self.adapter.fetch_ticker(symbol=symbol)
                payload = observation.payload if isinstance(observation.payload, dict) else None
                if not payload:
                    raise RuntimeError("empty_market_observation")
                rows.append(
                    {
                        "symbol": symbol,
                        "current_price": payload.get("last_price"),
                        "change_24h_percent": payload.get("price_change_percent"),
                        "high_24h": payload.get("high_price_24h"),
                        "low_24h": payload.get("low_price_24h"),
                        "volume_24h": payload.get("quote_volume"),
                        "provider_timestamp": _utc_from_ms(observation.exchange_timestamp_ms),
                        "server_received_timestamp": _utc_from_ms(observation.received_at_ms),
                        "freshness": "FRESH" if observation.quality == "OK" else observation.quality,
                        "data_delayed": observation.quality != "OK",
                    }
                )
            except Exception:  # Provider failures never manufacture values.
                failures += 1

        if rows:
            # Preserve unavailable symbols explicitly instead of replacing them
            # with fixture values or zeros.
            present = {row["symbol"] for row in rows}
            rows.extend(
                {
                    "symbol": symbol,
                    "current_price": None,
                    "change_24h_percent": None,
                    "high_24h": None,
                    "low_24h": None,
                    "volume_24h": None,
                    "provider_timestamp": None,
                    "server_received_timestamp": _utc_now(),
                    "freshness": "UNAVAILABLE",
                    "data_delayed": True,
                }
                for symbol in SYMBOLS
                if symbol not in present
            )
            body = {
                "schema": "nexus_public_market_snapshot_v1",
                "data_class": "LIVE_READ_ONLY",
                "provider": "binance_usdm_public",
                "read_only": True,
                "execution_controls": False,
                "credentials_required": False,
                "poll_interval_sec": int(self.cache_ttl_sec),
                "server_timestamp": _utc_now(),
                "symbols": rows,
                "provider_failures": failures,
                "fallback": "none",
            }
            self._cache, self._cached_at = body, self.clock()
            return body, 200

        if self._cache is not None:
            stale = {
                **self._cache,
                "server_timestamp": _utc_now(),
                "fallback": "last_known_value",
                "provider_failures": failures,
                "symbols": [
                    {**row, "freshness": "STALE", "data_delayed": True}
                    for row in self._cache["symbols"]
                ],
            }
            return stale, 200

        return (
            {
                "schema": "nexus_public_market_snapshot_v1",
                "data_class": "LIVE_READ_ONLY",
                "provider": "binance_usdm_public",
                "read_only": True,
                "execution_controls": False,
                "credentials_required": False,
                "server_timestamp": _utc_now(),
                "symbols": [],
                "provider_failures": failures,
                "fallback": "unavailable",
            },
            503,
        )

    def rankings(self, *, metric: str, limit: int) -> tuple[dict[str, Any], int]:
        """Rank only official 24h ticker facts; never synthesize NEXUS opinions."""
        payload, status = self.snapshot()
        rows = [
            row for row in payload.get("symbols", [])
            if row.get("current_price") is not None
        ]
        metric = metric if metric in {"gainers", "losers", "volume", "volatility", "liquidity"} else "gainers"
        if metric == "gainers":
            rows.sort(key=lambda row: row.get("change_24h_percent") or float("-inf"), reverse=True)
        elif metric == "losers":
            rows.sort(key=lambda row: row.get("change_24h_percent") or float("inf"))
        elif metric in {"volume", "liquidity"}:
            # Quote turnover is the public, consistently available liquidity proxy.
            rows.sort(key=lambda row: row.get("volume_24h") or float("-inf"), reverse=True)
        else:
            rows.sort(
                key=lambda row: (
                    ((row.get("high_24h") or 0) - (row.get("low_24h") or 0))
                    / (row.get("current_price") or 1)
                ),
                reverse=True,
            )
        return (
            {
                "schema": "nexus_public_market_ranking_v1",
                "data_class": "LIVE_READ_ONLY",
                "classification": "LIVE_API",
                "provider": payload.get("provider", "binance_usdm_public"),
                "ranking_type": metric,
                "ranking_label": {
                    "gainers": "24h gainers",
                    "losers": "24h losers",
                    "volume": "volume ranking",
                    "volatility": "volatility ranking",
                    "liquidity": "liquidity ranking",
                }[metric],
                "server_timestamp": payload.get("server_timestamp"),
                "freshness": "DATA_DELAYED" if payload.get("fallback") == "last_known_value" else "LIVE",
                "rows": rows[:max(1, min(limit, len(SYMBOLS)))],
                "runtime_ranking_available": False,
            },
            status,
        )


def build_public_market_snapshot_service() -> PublicMarketSnapshotService:
    return PublicMarketSnapshotService()


class PublicMarketTelemetryService:
    """Bounded, server-cached public derivatives and order-book telemetry."""

    def __init__(
        self,
        *,
        adapter: BinanceUsdmPublicAdapter | None = None,
        clock: Callable[[], float] = time.monotonic,
        cache_ttl_sec: float = POLL_INTERVAL_SEC,
    ) -> None:
        self.adapter = adapter or BinanceUsdmPublicAdapter(use_fixtures=False)
        self.clock = clock
        self.cache_ttl_sec = cache_ttl_sec
        self._cache: dict[tuple[str, str], tuple[dict[str, Any], float]] = {}

    def _cached(self, kind: str, symbol: str, loader: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], int]:
        symbol = symbol.upper()
        if symbol not in SYMBOLS:
            return self._unavailable(kind, symbol, "unsupported_allowlisted_symbol"), 400
        key = (kind, symbol)
        prior = self._cache.get(key)
        if prior and self.clock() - prior[1] < self.cache_ttl_sec:
            return prior[0], 200
        try:
            body = loader()
            body.update(
                {
                    "schema": f"nexus_public_market_{kind}_v1",
                    "data_class": "LIVE_READ_ONLY",
                    "classification": "LIVE_API",
                    "provider": "binance_usdm_public",
                    "symbol": symbol,
                    "server_timestamp": _utc_now(),
                    "freshness": "LIVE",
                    "fallback": "none",
                }
            )
            self._cache[key] = (body, self.clock())
            return body, 200
        except Exception:
            if prior:
                return {
                    **prior[0],
                    "server_timestamp": _utc_now(),
                    "freshness": "DATA_DELAYED",
                    "fallback": "last_known_value",
                }, 200
            return self._unavailable(kind, symbol, "provider_unavailable"), 503

    def _unavailable(self, kind: str, symbol: str, reason: str) -> dict[str, Any]:
        return {
            "schema": f"nexus_public_market_{kind}_v1",
            "data_class": "LIVE_READ_ONLY",
            "classification": "LIVE_API",
            "provider": "binance_usdm_public",
            "symbol": symbol,
            "server_timestamp": _utc_now(),
            "freshness": "UNAVAILABLE",
            "fallback": "unavailable",
            "reason": reason,
        }

    def instruments(self) -> tuple[dict[str, Any], int]:
        try:
            observation = self.adapter.fetch_instrument_catalog()
            instruments = [
                row for row in (observation.payload or {}).get("instruments", [])
                if row.get("symbol") in SYMBOLS and row.get("status") == "Trading"
            ]
            return {
                "schema": "nexus_public_market_instruments_v1",
                "data_class": "LIVE_READ_ONLY",
                "classification": "LIVE_API",
                "provider": "binance_usdm_public",
                "server_timestamp": _utc_now(),
                "freshness": "LIVE",
                "instruments": instruments,
            }, 200
        except Exception:
            return {
                "schema": "nexus_public_market_instruments_v1",
                "data_class": "LIVE_READ_ONLY",
                "classification": "LIVE_API",
                "provider": "binance_usdm_public",
                "server_timestamp": _utc_now(),
                "freshness": "UNAVAILABLE",
                "instruments": [],
            }, 503

    def derivatives(self, symbol: str) -> tuple[dict[str, Any], int]:
        def load() -> dict[str, Any]:
            mark = self.adapter.fetch_mark_index_price(symbol=symbol).payload or {}
            funding = self.adapter.fetch_funding(symbol=symbol).payload or {}
            interest = self.adapter.fetch_open_interest(symbol=symbol).payload or {}
            specs = self.adapter.fetch_contract_specs(symbol=symbol).payload or {}
            return {"mark_index": mark, "funding": funding, "open_interest": interest, "contract_specs": specs}
        return self._cached("derivatives", symbol, load)

    def liquidity(self, symbol: str) -> tuple[dict[str, Any], int]:
        def load() -> dict[str, Any]:
            book = self.adapter.fetch_order_book_summary(symbol=symbol).payload or {}
            bid, ask = book.get("best_bid"), book.get("best_ask")
            spread = (ask - bid) if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) else None
            spread_bps = ((spread / ((ask + bid) / 2)) * 10000) if spread is not None and ask + bid else None
            return {"order_book": book, "spread": spread, "spread_bps": spread_bps}
        return self._cached("liquidity", symbol, load)

    def liquidations(self, symbol: str) -> tuple[dict[str, Any], int]:
        return self._cached(
            "liquidations",
            symbol,
            lambda: {"events": (self.adapter.fetch_liquidations(symbol=symbol).payload or {}).get("liquidations", [])},
        )


def build_public_market_telemetry_service() -> PublicMarketTelemetryService:
    return PublicMarketTelemetryService()


class PublicMarketHistoryService:
    """Bounded, credential-free OHLCV history for the three supported symbols."""

    def __init__(
        self,
        *,
        adapter: BinanceUsdmPublicAdapter | None = None,
        clock: Callable[[], float] = time.monotonic,
        cache_ttl_sec: float = POLL_INTERVAL_SEC,
    ) -> None:
        self.adapter = adapter or BinanceUsdmPublicAdapter(use_fixtures=False)
        self.clock = clock
        self.cache_ttl_sec = cache_ttl_sec
        self._cache: dict[tuple[str, str, int], tuple[dict[str, Any], float]] = {}

    def history(self, *, symbol: str, interval: str, limit: int) -> tuple[dict[str, Any], int]:
        symbol = symbol.upper()
        interval = interval.lower()
        limit = max(HISTORY_LIMIT_MIN, min(HISTORY_LIMIT_MAX, int(limit)))
        if symbol not in SYMBOLS or interval not in HISTORY_INTERVALS:
            return (
                {
                    "schema": "nexus_public_market_history_v1",
                    "data_class": "LIVE_READ_ONLY",
                    "read_only": True,
                    "execution_controls": False,
                    "credentials_required": False,
                    "error": "unsupported_bounded_history_request",
                },
                400,
            )
        key = (symbol, interval, limit)
        cached = self._cache.get(key)
        if cached and self.clock() - cached[1] < self.cache_ttl_sec:
            return cached[0], 200
        try:
            observation = self.adapter.fetch_ohlcv(symbol=symbol, interval=interval, limit=limit)
            raw = observation.payload if isinstance(observation.payload, dict) else {}
            candles = raw.get("candles") if isinstance(raw, dict) else None
            if not isinstance(candles, list) or not candles:
                raise RuntimeError("empty_ohlcv_observation")
            body = {
                "schema": "nexus_public_market_history_v1",
                "data_class": "LIVE_READ_ONLY",
                "provider": "binance_usdm_public",
                "read_only": True,
                "execution_controls": False,
                "credentials_required": False,
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "provider_timestamp": _utc_from_ms(observation.exchange_timestamp_ms),
                "server_received_timestamp": _utc_from_ms(observation.received_at_ms),
                "server_timestamp": _utc_now(),
                # A completed 15m/1h candle can be older than the ticker
                # freshness threshold by design. Feed freshness therefore
                # represents this bounded public API fetch, while the candle
                # close time remains visible in each row.
                "freshness": "FRESH",
                "data_delayed": False,
                "candles": candles,
                "fallback": "none",
            }
            self._cache[key] = (body, self.clock())
            return body, 200
        except Exception:
            if cached:
                stale = {
                    **cached[0],
                    "server_timestamp": _utc_now(),
                    "freshness": "STALE",
                    "data_delayed": True,
                    "fallback": "last_known_value",
                }
                return stale, 200
            return (
                {
                    "schema": "nexus_public_market_history_v1",
                    "data_class": "LIVE_READ_ONLY",
                    "read_only": True,
                    "execution_controls": False,
                    "credentials_required": False,
                    "symbol": symbol,
                    "interval": interval,
                    "server_timestamp": _utc_now(),
                    "freshness": "UNAVAILABLE",
                    "data_delayed": True,
                    "candles": [],
                    "fallback": "unavailable",
                },
                503,
            )


def build_public_market_history_service() -> PublicMarketHistoryService:
    return PublicMarketHistoryService()
