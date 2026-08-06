"""Bybit official public V5 read-only market adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_official_market_adapters.constitution import (
    OfficialReadOnlyConstitution,
    bybit_constitution,
)
from backend.nexus_official_market_adapters.constants import (
    DATA_MODE_FIXTURE,
    DATA_MODE_LIVE_READ_ONLY,
    QUALITY_UNAVAILABLE,
)
from backend.nexus_official_market_adapters.contracts import (
    AdapterManifest,
    OfficialReadOnlyMarketAdapter,
    assert_mode,
)
from backend.nexus_official_market_adapters.envelope import (
    MarketObservation,
    safe_float,
    unavailable,
    wrap_ok,
)
from backend.nexus_official_market_adapters.fixtures_io import load_fixture
from backend.nexus_official_market_adapters.transport import BoundedHttpClient

ADAPTER_ID = "bybit_public_v5"
PROVIDER = "bybit"
BASE_URL = "https://api.bybit.com"
HOST = "api.bybit.com"

BYBIT_PUBLIC_WS_TOPICS = (
    "tickers",
    "orderbook.1",
    "orderbook.50",
    "kline.1",
    "kline.5",
    "publicTrade",
    "allLiquidation",
)

BYBIT_PUBLIC_REST = (
    "/v5/market/instruments-info",
    "/v5/market/tickers",
    "/v5/market/kline",
    "/v5/market/mark-price-kline",
    "/v5/market/index-price-kline",
    "/v5/market/orderbook",
    "/v5/market/recent-trade",
    "/v5/market/funding/history",
    "/v5/market/open-interest",
)

_INTERVAL_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "60m": "60",
    "1h": "60",
    "4h": "240",
    "1d": "D",
}


def _exchange_ts(payload: dict[str, Any]) -> int | None:
    raw = payload.get("time")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@dataclass
class BybitPublicV5Adapter(OfficialReadOnlyMarketAdapter):
    """Official Bybit public REST adapter — no API key, no write."""

    use_fixtures: bool = True
    constitution: OfficialReadOnlyConstitution = field(default_factory=bybit_constitution)
    http: BoundedHttpClient | None = None
    base_url: str = BASE_URL
    _mode: str = field(default=DATA_MODE_FIXTURE, init=False)

    def __post_init__(self) -> None:
        if self.http is None:
            self.http = BoundedHttpClient(constitution=self.constitution)
        self._mode = DATA_MODE_FIXTURE if self.use_fixtures else DATA_MODE_LIVE_READ_ONLY

    @property
    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            official=True,
            read_only=True,
            secret_required=False,
            account_endpoints=(),
            exchange_write_endpoints=(),
            public_rest_endpoints=BYBIT_PUBLIC_REST,
            public_ws_topics=BYBIT_PUBLIC_WS_TOPICS,
            capabilities=(
                "instrument_catalog",
                "ticker",
                "mark_index_price",
                "ohlcv",
                "public_trades",
                "funding",
                "open_interest",
                "order_book_summary",
                "liquidation",
                "listing_status",
                "contract_specs",
            ),
            supports_live_read_only=True,
            contract_only=False,
            notes=(
                "liquidation REST unavailable; official WS topic allLiquidation only",
                "missing fields stay null — never filled with 0",
            ),
        )

    def set_data_mode(self, mode: str) -> None:
        self._mode = assert_mode(mode)
        self.use_fixtures = self._mode == DATA_MODE_FIXTURE

    def data_mode(self) -> str:
        return self._mode

    def capability_matrix(self) -> dict[str, str]:
        return {
            "instrument_catalog": "implemented",
            "ticker": "implemented",
            "mark_index_price": "implemented",
            "ohlcv": "implemented",
            "public_trades": "implemented",
            "funding": "implemented",
            "open_interest": "implemented",
            "order_book_summary": "implemented",
            "liquidation": "ws_only",
            "listing_status": "implemented",
            "contract_specs": "implemented",
        }

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.use_fixtures:
            return self._fixture_payload(path)
        assert self.http is not None
        url = f"{self.base_url.rstrip('/')}{path}"
        return self.http.get(url, params=params or {})

    def _fixture_payload(self, path: str) -> dict[str, Any]:
        mapping = {
            "/v5/market/instruments-info": "instruments_info.json",
            "/v5/market/tickers": "tickers.json",
            "/v5/market/kline": "kline.json",
            "/v5/market/mark-price-kline": "mark_price_kline.json",
            "/v5/market/index-price-kline": "index_price_kline.json",
            "/v5/market/orderbook": "orderbook.json",
            "/v5/market/recent-trade": "recent_trade.json",
            "/v5/market/funding/history": "funding.json",
            "/v5/market/open-interest": "open_interest.json",
        }
        name = mapping.get(path)
        if not name:
            return {"ok": False, "error": f"no_fixture_for:{path}"}
        return {"ok": True, "json": load_fixture("bybit", name)}

    def _raw_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = self._get(path, params)
        if not raw.get("ok", True) and "json" not in raw:
            raise RuntimeError(str(raw.get("error") or "request_failed"))
        payload = raw.get("json") or raw
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected_payload_type")
        return payload

    def fetch_instrument_catalog(self, *, category: str | None = None) -> MarketObservation:
        cat = category or "linear"
        payload = self._raw_json("/v5/market/instruments-info", {"category": cat})
        rows = (payload.get("result") or {}).get("list") or []
        instruments = []
        for row in rows:
            instruments.append(
                {
                    "symbol": row.get("symbol"),
                    "status": row.get("status"),
                    "base_coin": row.get("baseCoin"),
                    "quote_coin": row.get("quoteCoin"),
                    "contract_type": row.get("contractType"),
                    "settle_coin": row.get("settleCoin"),
                    "launch_time_ms": row.get("launchTime"),
                }
            )
        return wrap_ok(
            capability="instrument_catalog",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/v5/market/instruments-info",
            host=HOST,
            payload={"category": cat, "instruments": instruments},
            data_mode=self._mode,
            exchange_timestamp_ms=_exchange_ts(payload),
        )

    def fetch_ticker(self, *, symbol: str) -> MarketObservation:
        payload = self._raw_json("/v5/market/tickers", {"category": "linear", "symbol": symbol})
        rows = (payload.get("result") or {}).get("list") or []
        row = next((r for r in rows if r.get("symbol") == symbol), rows[0] if rows else None)
        if row is None:
            return unavailable(
                capability="ticker",
                adapter_id=ADAPTER_ID,
                provider=PROVIDER,
                reason="symbol_not_in_response",
                data_mode=self._mode,
                symbol=symbol,
                endpoint="/v5/market/tickers",
                host=HOST,
            )
        body = {
            "symbol": row.get("symbol"),
            "last_price": safe_float(row.get("lastPrice")),
            "bid1_price": safe_float(row.get("bid1Price")),
            "ask1_price": safe_float(row.get("ask1Price")),
            "volume_24h": safe_float(row.get("volume24h")),
            "turnover_24h": safe_float(row.get("turnover24h")),
            "price_24h_pct": safe_float(row.get("price24hPcnt")),
        }
        return wrap_ok(
            capability="ticker",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/v5/market/tickers",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=_exchange_ts(payload),
            symbol=symbol,
        )

    def fetch_mark_index_price(self, *, symbol: str) -> MarketObservation:
        payload = self._raw_json("/v5/market/tickers", {"category": "linear", "symbol": symbol})
        rows = (payload.get("result") or {}).get("list") or []
        row = next((r for r in rows if r.get("symbol") == symbol), rows[0] if rows else None)
        if row is None:
            return unavailable(
                capability="mark_index_price",
                adapter_id=ADAPTER_ID,
                provider=PROVIDER,
                reason="symbol_not_in_response",
                data_mode=self._mode,
                symbol=symbol,
                endpoint="/v5/market/tickers",
                host=HOST,
            )
        body = {
            "symbol": row.get("symbol"),
            "mark_price": safe_float(row.get("markPrice")),
            "index_price": safe_float(row.get("indexPrice")),
        }
        return wrap_ok(
            capability="mark_index_price",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/v5/market/tickers",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=_exchange_ts(payload),
            symbol=symbol,
            notes=["mark/index from public tickers; REST not assumed always correct"],
        )

    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        interval: str = "5m",
        limit: int = 10,
    ) -> MarketObservation:
        bybit_interval = _INTERVAL_MAP.get(interval, interval)
        payload = self._raw_json(
            "/v5/market/kline",
            {"category": "linear", "symbol": symbol, "interval": bybit_interval, "limit": limit},
        )
        rows = (payload.get("result") or {}).get("list") or []
        candles = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 5:
                continue
            candles.append(
                {
                    "start_ms": int(row[0]) if str(row[0]).isdigit() else None,
                    "open": safe_float(row[1]),
                    "high": safe_float(row[2]),
                    "low": safe_float(row[3]),
                    "close": safe_float(row[4]),
                    "volume": safe_float(row[5]) if len(row) > 5 else None,
                    "turnover": safe_float(row[6]) if len(row) > 6 else None,
                }
            )
        return wrap_ok(
            capability="ohlcv",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/v5/market/kline",
            host=HOST,
            payload={"symbol": symbol, "interval": interval, "candles": candles},
            data_mode=self._mode,
            exchange_timestamp_ms=_exchange_ts(payload),
            symbol=symbol,
        )

    def fetch_public_trades(self, *, symbol: str, limit: int = 20) -> MarketObservation:
        payload = self._raw_json(
            "/v5/market/recent-trade",
            {"category": "linear", "symbol": symbol, "limit": limit},
        )
        rows = (payload.get("result") or {}).get("list") or []
        trades = []
        for row in rows:
            trades.append(
                {
                    "trade_id": row.get("execId") or row.get("id"),
                    "price": safe_float(row.get("price")),
                    "size": safe_float(row.get("size")),
                    "side": row.get("side"),
                    "time_ms": int(row["time"]) if str(row.get("time") or "").isdigit() else None,
                }
            )
        return wrap_ok(
            capability="public_trades",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/v5/market/recent-trade",
            host=HOST,
            payload={"symbol": symbol, "trades": trades},
            data_mode=self._mode,
            exchange_timestamp_ms=_exchange_ts(payload),
            symbol=symbol,
        )

    def fetch_funding(self, *, symbol: str) -> MarketObservation:
        payload = self._raw_json(
            "/v5/market/funding/history",
            {"category": "linear", "symbol": symbol, "limit": 1},
        )
        rows = (payload.get("result") or {}).get("list") or []
        row = rows[0] if rows else None
        body = {
            "symbol": symbol,
            "funding_rate": safe_float(row.get("fundingRate")) if row else None,
            "funding_rate_timestamp_ms": (
                int(row["fundingRateTimestamp"])
                if row and str(row.get("fundingRateTimestamp") or "").isdigit()
                else None
            ),
        }
        return wrap_ok(
            capability="funding",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/v5/market/funding/history",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=_exchange_ts(payload),
            symbol=symbol,
        )

    def fetch_open_interest(self, *, symbol: str) -> MarketObservation:
        payload = self._raw_json(
            "/v5/market/open-interest",
            {"category": "linear", "symbol": symbol, "intervalTime": "5min", "limit": 1},
        )
        rows = (payload.get("result") or {}).get("list") or []
        row = rows[0] if rows else None
        body = {
            "symbol": symbol,
            "open_interest": safe_float(row.get("openInterest")) if row else None,
            "timestamp_ms": (
                int(row["timestamp"]) if row and str(row.get("timestamp") or "").isdigit() else None
            ),
        }
        return wrap_ok(
            capability="open_interest",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/v5/market/open-interest",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=_exchange_ts(payload),
            symbol=symbol,
        )

    def fetch_order_book_summary(self, *, symbol: str, depth: int = 25) -> MarketObservation:
        payload = self._raw_json(
            "/v5/market/orderbook",
            {"category": "linear", "symbol": symbol, "limit": depth},
        )
        result = payload.get("result") or {}
        bids = result.get("b") or []
        asks = result.get("a") or []
        bid_depth = None
        ask_depth = None
        if bids:
            vals = [safe_float(x[1]) for x in bids if isinstance(x, list) and len(x) >= 2]
            present = [v for v in vals if v is not None]
            bid_depth = sum(present) if present else None
        if asks:
            vals = [safe_float(x[1]) for x in asks if isinstance(x, list) and len(x) >= 2]
            present = [v for v in vals if v is not None]
            ask_depth = sum(present) if present else None
        best_bid = safe_float(bids[0][0]) if bids and isinstance(bids[0], list) else None
        best_ask = safe_float(asks[0][0]) if asks and isinstance(asks[0], list) else None
        body = {
            "symbol": symbol,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "levels_bids": len(bids) if bids else None,
            "levels_asks": len(asks) if asks else None,
        }
        return wrap_ok(
            capability="order_book_summary",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/v5/market/orderbook",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=_exchange_ts(payload),
            symbol=symbol,
        )

    def fetch_liquidations(self, *, symbol: str, limit: int = 20) -> MarketObservation:
        del limit
        # Honest: Bybit public REST has no liquidation history endpoint in allowlist.
        # Official public WS topic `allLiquidation` exists — mark UNAVAILABLE for REST.
        obs = unavailable(
            capability="liquidation",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            reason="bybit_liquidation_rest_unavailable_ws_only:allLiquidation",
            data_mode=self._mode,
            symbol=symbol,
            endpoint="ws:allLiquidation",
            host=HOST,
        )
        # Fix access_method for fixture mode unavailable — already handled.
        # Ensure quality is UNAVAILABLE (not fabricated).
        assert obs.quality == QUALITY_UNAVAILABLE
        assert obs.payload is None
        return obs

    def fetch_listing_status(self, *, symbol: str) -> MarketObservation:
        payload = self._raw_json("/v5/market/instruments-info", {"category": "linear", "symbol": symbol})
        rows = (payload.get("result") or {}).get("list") or []
        row = next((r for r in rows if r.get("symbol") == symbol), rows[0] if rows else None)
        if row is None:
            return unavailable(
                capability="listing_status",
                adapter_id=ADAPTER_ID,
                provider=PROVIDER,
                reason="symbol_not_found",
                data_mode=self._mode,
                symbol=symbol,
                endpoint="/v5/market/instruments-info",
                host=HOST,
            )
        body = {
            "symbol": row.get("symbol"),
            "status": row.get("status"),
            "listed": row.get("status") == "Trading",
        }
        return wrap_ok(
            capability="listing_status",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/v5/market/instruments-info",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=_exchange_ts(payload),
            symbol=symbol,
        )

    def fetch_contract_specs(self, *, symbol: str) -> MarketObservation:
        payload = self._raw_json("/v5/market/instruments-info", {"category": "linear", "symbol": symbol})
        rows = (payload.get("result") or {}).get("list") or []
        row = next((r for r in rows if r.get("symbol") == symbol), rows[0] if rows else None)
        if row is None:
            return unavailable(
                capability="contract_specs",
                adapter_id=ADAPTER_ID,
                provider=PROVIDER,
                reason="symbol_not_found",
                data_mode=self._mode,
                symbol=symbol,
                endpoint="/v5/market/instruments-info",
                host=HOST,
            )
        body = {
            "symbol": row.get("symbol"),
            "contract_type": row.get("contractType"),
            "price_filter": row.get("priceFilter"),
            "lot_size_filter": row.get("lotSizeFilter"),
            "leverage_filter": row.get("leverageFilter"),
            "funding_interval": row.get("fundingInterval"),
            "settle_coin": row.get("settleCoin"),
            "price_scale": row.get("priceScale"),
        }
        return wrap_ok(
            capability="contract_specs",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/v5/market/instruments-info",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=_exchange_ts(payload),
            symbol=symbol,
        )

    def stats(self) -> dict[str, Any]:
        return {
            "adapter_id": ADAPTER_ID,
            "data_mode": self._mode,
            "constitution": self.constitution.snapshot(),
            "http": self.http.stats() if self.http else {},
        }


__all__ = ["BybitPublicV5Adapter", "ADAPTER_ID", "BYBIT_PUBLIC_REST", "BYBIT_PUBLIC_WS_TOPICS"]
