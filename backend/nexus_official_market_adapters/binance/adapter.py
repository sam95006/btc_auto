"""Binance USD-M Futures official public read-only market adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_official_market_adapters.constitution import (
    OfficialReadOnlyConstitution,
    binance_usdm_constitution,
)
from backend.nexus_official_market_adapters.constants import (
    DATA_MODE_FIXTURE,
    DATA_MODE_LIVE_READ_ONLY,
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

ADAPTER_ID = "binance_usdm_public"
PROVIDER = "binance"
BASE_URL = "https://fapi.binance.com"
HOST = "fapi.binance.com"

BINANCE_PUBLIC_REST = (
    "/fapi/v1/exchangeInfo",
    "/fapi/v1/ticker/24hr",
    "/fapi/v1/premiumIndex",
    "/fapi/v1/klines",
    "/fapi/v1/trades",
    "/fapi/v1/aggTrades",
    "/fapi/v1/depth",
    "/fapi/v1/fundingRate",
    "/fapi/v1/openInterest",
    "/fapi/v1/forceOrders",
)

BINANCE_PUBLIC_WS_TOPICS = (
    "bookTicker",
    "markPrice",
    "kline_5m",
    "aggTrade",
    "depth5",
    "forceOrder",
)

_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


@dataclass
class BinanceUsdmPublicAdapter(OfficialReadOnlyMarketAdapter):
    """Official Binance USD-M public REST — no API key, no write."""

    use_fixtures: bool = True
    constitution: OfficialReadOnlyConstitution = field(default_factory=binance_usdm_constitution)
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
            public_rest_endpoints=BINANCE_PUBLIC_REST,
            public_ws_topics=BINANCE_PUBLIC_WS_TOPICS,
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
                "forceOrders is the official public liquidation endpoint",
                "missing fields stay null — never filled with 0",
            ),
        )

    def set_data_mode(self, mode: str) -> None:
        self._mode = assert_mode(mode)
        self.use_fixtures = self._mode == DATA_MODE_FIXTURE

    def data_mode(self) -> str:
        return self._mode

    def capability_matrix(self) -> dict[str, str]:
        return {cap: "implemented" for cap in self.manifest.capabilities}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.use_fixtures:
            return self._fixture_payload(path)
        assert self.http is not None
        url = f"{self.base_url.rstrip('/')}{path}"
        return self.http.get(url, params=params or {})

    def _fixture_payload(self, path: str) -> dict[str, Any]:
        mapping = {
            "/fapi/v1/exchangeInfo": "exchange_info.json",
            "/fapi/v1/ticker/24hr": "ticker_24hr.json",
            "/fapi/v1/premiumIndex": "premium_index.json",
            "/fapi/v1/klines": "klines.json",
            "/fapi/v1/trades": "trades.json",
            "/fapi/v1/depth": "depth.json",
            "/fapi/v1/fundingRate": "funding_rate.json",
            "/fapi/v1/openInterest": "open_interest.json",
            "/fapi/v1/forceOrders": "force_orders.json",
        }
        name = mapping.get(path)
        if not name:
            return {"ok": False, "error": f"no_fixture_for:{path}"}
        return {"ok": True, "json": load_fixture("binance", name)}

    def _raw(self, path: str, params: dict[str, Any] | None = None) -> Any:
        raw = self._get(path, params)
        if not raw.get("ok", True) and "json" not in raw:
            raise RuntimeError(str(raw.get("error") or "request_failed"))
        return raw.get("json") if "json" in raw else raw

    def fetch_instrument_catalog(self, *, category: str | None = None) -> MarketObservation:
        del category
        payload = self._raw("/fapi/v1/exchangeInfo")
        assert isinstance(payload, dict)
        symbols = payload.get("symbols") or []
        instruments = []
        for row in symbols:
            filters = {str(f.get("filterType")): f for f in (row.get("filters") or []) if f.get("filterType")}
            price_f = filters.get("PRICE_FILTER") or {}
            lot_f = filters.get("LOT_SIZE") or filters.get("MARKET_LOT_SIZE") or {}
            notional_f = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
            onboard = row.get("onboardDate")
            launch_ms = int(onboard) if onboard is not None else None
            status = row.get("status")
            # Normalize Binance TRADING → Trading for universe gate vocabulary.
            status_norm = "Trading" if str(status).upper() == "TRADING" else status
            instruments.append(
                {
                    "symbol": row.get("symbol"),
                    "status": status_norm,
                    "base_asset": row.get("baseAsset"),
                    "base_coin": row.get("baseAsset"),
                    "quote_asset": row.get("quoteAsset"),
                    "quote_coin": row.get("quoteAsset"),
                    "contract_type": row.get("contractType"),
                    "margin_asset": row.get("marginAsset"),
                    "launch_time_ms": launch_ms,
                    "tick_size": safe_float(price_f.get("tickSize")),
                    "lot_size": safe_float(lot_f.get("stepSize") or lot_f.get("minQty")),
                    "min_notional": safe_float(
                        notional_f.get("notional") or notional_f.get("minNotional")
                    ),
                }
            )
        return wrap_ok(
            capability="instrument_catalog",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/exchangeInfo",
            host=HOST,
            payload={"instruments": instruments},
            data_mode=self._mode,
            exchange_timestamp_ms=int(payload["serverTime"]) if payload.get("serverTime") else None,
        )

    def fetch_ticker(self, *, symbol: str) -> MarketObservation:
        payload = self._raw("/fapi/v1/ticker/24hr", {"symbol": symbol})
        if isinstance(payload, list):
            row = next((r for r in payload if r.get("symbol") == symbol), None)
        else:
            row = payload if isinstance(payload, dict) else None
        if not row:
            return unavailable(
                capability="ticker",
                adapter_id=ADAPTER_ID,
                provider=PROVIDER,
                reason="symbol_not_in_response",
                data_mode=self._mode,
                symbol=symbol,
                endpoint="/fapi/v1/ticker/24hr",
                host=HOST,
            )
        bid = safe_float(row.get("bidPrice"))
        ask = safe_float(row.get("askPrice"))
        turnover = safe_float(row.get("quoteVolume"))
        trade_count = row.get("count")
        try:
            trade_count_i = int(trade_count) if trade_count is not None else None
        except (TypeError, ValueError):
            trade_count_i = None
        body = {
            "symbol": row.get("symbol"),
            "last_price": safe_float(row.get("lastPrice")),
            "bid_price": bid,
            "ask_price": ask,
            "bid1_price": bid,
            "ask1_price": ask,
            "volume": safe_float(row.get("volume")),
            "quote_volume": turnover,
            "turnover_24h": turnover,
            "trade_count_24h": trade_count_i,
            "price_change_percent": safe_float(row.get("priceChangePercent")),
        }
        close_time = row.get("closeTime")
        return wrap_ok(
            capability="ticker",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/ticker/24hr",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=int(close_time) if close_time is not None else None,
            symbol=symbol,
        )

    def fetch_mark_index_price(self, *, symbol: str) -> MarketObservation:
        payload = self._raw("/fapi/v1/premiumIndex", {"symbol": symbol})
        if isinstance(payload, list):
            row = next((r for r in payload if r.get("symbol") == symbol), None)
        else:
            row = payload if isinstance(payload, dict) else None
        if not row:
            return unavailable(
                capability="mark_index_price",
                adapter_id=ADAPTER_ID,
                provider=PROVIDER,
                reason="symbol_not_in_response",
                data_mode=self._mode,
                symbol=symbol,
                endpoint="/fapi/v1/premiumIndex",
                host=HOST,
            )
        body = {
            "symbol": row.get("symbol"),
            "mark_price": safe_float(row.get("markPrice")),
            "index_price": safe_float(row.get("indexPrice")),
            "last_funding_rate": safe_float(row.get("lastFundingRate")),
        }
        ts = row.get("time")
        return wrap_ok(
            capability="mark_index_price",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/premiumIndex",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=int(ts) if ts is not None else None,
            symbol=symbol,
        )

    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        interval: str = "5m",
        limit: int = 10,
    ) -> MarketObservation:
        iv = _INTERVAL_MAP.get(interval, interval)
        payload = self._raw(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": iv, "limit": limit},
        )
        rows = payload if isinstance(payload, list) else []
        candles = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                continue
            candles.append(
                {
                    "open_time_ms": int(row[0]) if row[0] is not None else None,
                    "open": safe_float(row[1]),
                    "high": safe_float(row[2]),
                    "low": safe_float(row[3]),
                    "close": safe_float(row[4]),
                    "volume": safe_float(row[5]),
                    "close_time_ms": int(row[6]) if len(row) > 6 and row[6] is not None else None,
                }
            )
        last_ts = candles[0]["close_time_ms"] if candles else None
        return wrap_ok(
            capability="ohlcv",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/klines",
            host=HOST,
            payload={"symbol": symbol, "interval": interval, "candles": candles},
            data_mode=self._mode,
            exchange_timestamp_ms=last_ts,
            symbol=symbol,
        )

    def fetch_public_trades(self, *, symbol: str, limit: int = 20) -> MarketObservation:
        payload = self._raw("/fapi/v1/trades", {"symbol": symbol, "limit": limit})
        rows = payload if isinstance(payload, list) else []
        trades = []
        for row in rows:
            trades.append(
                {
                    "trade_id": row.get("id"),
                    "price": safe_float(row.get("price")),
                    "qty": safe_float(row.get("qty")),
                    "time_ms": int(row["time"]) if row.get("time") is not None else None,
                    "is_buyer_maker": row.get("isBuyerMaker"),
                }
            )
        last_ts = trades[-1]["time_ms"] if trades else None
        return wrap_ok(
            capability="public_trades",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/trades",
            host=HOST,
            payload={"symbol": symbol, "trades": trades},
            data_mode=self._mode,
            exchange_timestamp_ms=last_ts,
            symbol=symbol,
        )

    def fetch_funding(self, *, symbol: str) -> MarketObservation:
        payload = self._raw("/fapi/v1/fundingRate", {"symbol": symbol, "limit": 1})
        rows = payload if isinstance(payload, list) else []
        row = rows[0] if rows else None
        body = {
            "symbol": symbol,
            "funding_rate": safe_float(row.get("fundingRate")) if row else None,
            "funding_time_ms": int(row["fundingTime"]) if row and row.get("fundingTime") is not None else None,
        }
        return wrap_ok(
            capability="funding",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/fundingRate",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=body["funding_time_ms"],
            symbol=symbol,
        )

    def fetch_open_interest(self, *, symbol: str) -> MarketObservation:
        payload = self._raw("/fapi/v1/openInterest", {"symbol": symbol})
        if not isinstance(payload, dict):
            return unavailable(
                capability="open_interest",
                adapter_id=ADAPTER_ID,
                provider=PROVIDER,
                reason="unexpected_payload",
                data_mode=self._mode,
                symbol=symbol,
                endpoint="/fapi/v1/openInterest",
                host=HOST,
            )
        body = {
            "symbol": payload.get("symbol") or symbol,
            "open_interest": safe_float(payload.get("openInterest")),
            "time_ms": int(payload["time"]) if payload.get("time") is not None else None,
        }
        return wrap_ok(
            capability="open_interest",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/openInterest",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=body["time_ms"],
            symbol=symbol,
        )

    def fetch_order_book_summary(self, *, symbol: str, depth: int = 25) -> MarketObservation:
        limit = 5 if depth <= 5 else 10 if depth <= 10 else 20 if depth <= 20 else 50
        payload = self._raw("/fapi/v1/depth", {"symbol": symbol, "limit": limit})
        if not isinstance(payload, dict):
            return unavailable(
                capability="order_book_summary",
                adapter_id=ADAPTER_ID,
                provider=PROVIDER,
                reason="unexpected_payload",
                data_mode=self._mode,
                symbol=symbol,
                endpoint="/fapi/v1/depth",
                host=HOST,
            )
        bids = payload.get("bids") or []
        asks = payload.get("asks") or []
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
        body = {
            "symbol": symbol,
            "best_bid": safe_float(bids[0][0]) if bids else None,
            "best_ask": safe_float(asks[0][0]) if asks else None,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "levels_bids": len(bids) if bids else None,
            "levels_asks": len(asks) if asks else None,
            "last_update_id": payload.get("lastUpdateId"),
        }
        return wrap_ok(
            capability="order_book_summary",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/depth",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=None,  # depth payload has no exchange time — degrade honestly
            symbol=symbol,
            notes=["depth response lacks exchange timestamp; freshness DEGRADED"],
        )

    def fetch_liquidations(self, *, symbol: str, limit: int = 20) -> MarketObservation:
        payload = self._raw(
            "/fapi/v1/forceOrders",
            {"symbol": symbol, "limit": min(limit, 100)},
        )
        rows = payload if isinstance(payload, list) else []
        events = []
        for row in rows:
            events.append(
                {
                    "symbol": row.get("symbol"),
                    "side": row.get("side"),
                    "price": safe_float(row.get("price")),
                    "orig_qty": safe_float(row.get("origQty")),
                    "executed_qty": safe_float(row.get("executedQty")),
                    "average_price": safe_float(row.get("averagePrice")),
                    "status": row.get("status"),
                    "time_ms": int(row["time"]) if row.get("time") is not None else None,
                }
            )
        last_ts = events[0]["time_ms"] if events else None
        return wrap_ok(
            capability="liquidation",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/forceOrders",
            host=HOST,
            payload={"symbol": symbol, "liquidations": events},
            data_mode=self._mode,
            exchange_timestamp_ms=last_ts,
            symbol=symbol,
        )

    def fetch_listing_status(self, *, symbol: str) -> MarketObservation:
        payload = self._raw("/fapi/v1/exchangeInfo")
        assert isinstance(payload, dict)
        rows = payload.get("symbols") or []
        row = next((r for r in rows if r.get("symbol") == symbol), None)
        if row is None:
            return unavailable(
                capability="listing_status",
                adapter_id=ADAPTER_ID,
                provider=PROVIDER,
                reason="symbol_not_found",
                data_mode=self._mode,
                symbol=symbol,
                endpoint="/fapi/v1/exchangeInfo",
                host=HOST,
            )
        body = {
            "symbol": row.get("symbol"),
            "status": row.get("status"),
            "listed": row.get("status") == "TRADING",
        }
        return wrap_ok(
            capability="listing_status",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/exchangeInfo",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=int(payload["serverTime"]) if payload.get("serverTime") else None,
            symbol=symbol,
        )

    def fetch_contract_specs(self, *, symbol: str) -> MarketObservation:
        payload = self._raw("/fapi/v1/exchangeInfo")
        assert isinstance(payload, dict)
        rows = payload.get("symbols") or []
        row = next((r for r in rows if r.get("symbol") == symbol), None)
        if row is None:
            return unavailable(
                capability="contract_specs",
                adapter_id=ADAPTER_ID,
                provider=PROVIDER,
                reason="symbol_not_found",
                data_mode=self._mode,
                symbol=symbol,
                endpoint="/fapi/v1/exchangeInfo",
                host=HOST,
            )
        body = {
            "symbol": row.get("symbol"),
            "contract_type": row.get("contractType"),
            "filters": row.get("filters"),
            "price_precision": row.get("pricePrecision"),
            "quantity_precision": row.get("quantityPrecision"),
            "margin_asset": row.get("marginAsset"),
            "maint_margin_percent": safe_float(row.get("maintMarginPercent")),
            "required_margin_percent": safe_float(row.get("requiredMarginPercent")),
        }
        return wrap_ok(
            capability="contract_specs",
            adapter_id=ADAPTER_ID,
            provider=PROVIDER,
            endpoint="/fapi/v1/exchangeInfo",
            host=HOST,
            payload=body,
            data_mode=self._mode,
            exchange_timestamp_ms=int(payload["serverTime"]) if payload.get("serverTime") else None,
            symbol=symbol,
        )

    def stats(self) -> dict[str, Any]:
        return {
            "adapter_id": ADAPTER_ID,
            "data_mode": self._mode,
            "constitution": self.constitution.snapshot(),
            "http": self.http.stats() if self.http else {},
        }


__all__ = ["BinanceUsdmPublicAdapter", "ADAPTER_ID", "BINANCE_PUBLIC_REST", "BINANCE_PUBLIC_WS_TOPICS"]
