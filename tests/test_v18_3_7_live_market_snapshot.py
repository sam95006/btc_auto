"""Read-only market telemetry contract and stale-fallback tests."""
from __future__ import annotations

from flask import Flask

from backend.nexus_official_market_adapters.envelope import MarketObservation, SourceLineage
from backend.nexus_product_backend.market_snapshot import (
    SYMBOLS,
    PublicMarketHistoryService,
    PublicMarketSnapshotService,
)
from backend.nexus_product_backend.routes import register_product_alpha_routes


class _Adapter:
    def __init__(self) -> None:
        self.fail = False
        self.calls = 0

    def fetch_ticker(self, *, symbol: str) -> MarketObservation:
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider_timeout")
        return MarketObservation(
            capability="ticker",
            symbol=symbol,
            payload={
                "last_price": 100.0 + self.calls,
                "price_change_percent": 1.25,
                "high_price_24h": 110.0,
                "low_price_24h": 90.0,
                "quote_volume": 1_000_000.0,
            },
            quality="OK",
            data_mode="LIVE_READ_ONLY",
            source_lineage=SourceLineage(
                provider="binance",
                adapter_id="binance_usdm_public",
                endpoint="/fapi/v1/ticker/24hr",
                access_method="official_rest_api",
                host="fapi.binance.com",
            ),
            received_at_ms=1_700_000_000_000,
            exchange_timestamp_ms=1_700_000_000_000,
        )

    def fetch_ohlcv(self, *, symbol: str, interval: str, limit: int) -> MarketObservation:
        return MarketObservation(
            capability="ohlcv",
            symbol=symbol,
            payload={
                "symbol": symbol,
                "interval": interval,
                "candles": [
                    {
                        "open_time_ms": 1_700_000_000_000 + i,
                        "open": 100.0,
                        "high": 110.0,
                        "low": 90.0,
                        "close": 101.0,
                        "volume": 1000.0,
                        "close_time_ms": 1_700_000_001_000 + i,
                    }
                    for i in range(limit)
                ],
            },
            quality="OK",
            data_mode="LIVE_READ_ONLY",
            source_lineage=SourceLineage(
                provider="binance",
                adapter_id="binance_usdm_public",
                endpoint="/fapi/v1/klines",
                access_method="official_rest_api",
                host="fapi.binance.com",
            ),
            received_at_ms=1_700_000_001_000,
            exchange_timestamp_ms=1_700_000_001_000,
        )


def test_snapshot_is_public_read_only_and_complete():
    adapter = _Adapter()
    service = PublicMarketSnapshotService(adapter=adapter, cache_ttl_sec=0)

    payload, status = service.snapshot()

    assert status == 200
    assert payload["read_only"] is True
    assert payload["execution_controls"] is False
    assert payload["credentials_required"] is False
    assert [row["symbol"] for row in payload["symbols"]] == list(SYMBOLS)
    assert all(row["freshness"] == "FRESH" for row in payload["symbols"])
    assert all(
        {"current_price", "change_24h_percent", "high_24h", "low_24h", "volume_24h",
         "provider_timestamp", "server_received_timestamp"} <= set(row)
        for row in payload["symbols"]
    )


def test_snapshot_keeps_last_known_values_when_provider_fails():
    adapter = _Adapter()
    service = PublicMarketSnapshotService(adapter=adapter, cache_ttl_sec=0)
    first, status = service.snapshot()
    assert status == 200

    adapter.fail = True
    fallback, status = service.snapshot()

    assert status == 200
    assert fallback["fallback"] == "last_known_value"
    assert all(row["freshness"] == "STALE" and row["data_delayed"] for row in fallback["symbols"])
    assert [row["current_price"] for row in fallback["symbols"]] == [
        row["current_price"] for row in first["symbols"]
    ]


def test_snapshot_returns_unavailable_without_cached_values():
    adapter = _Adapter()
    adapter.fail = True
    payload, status = PublicMarketSnapshotService(adapter=adapter).snapshot()

    assert status == 503
    assert payload["fallback"] == "unavailable"
    assert payload["symbols"] == []


def test_snapshot_route_has_no_session_or_execution_requirement():
    app = Flask(__name__)
    app.config["NEXUS_PUBLIC_MARKET_SNAPSHOT_SERVICE"] = PublicMarketSnapshotService(
        adapter=_Adapter(), cache_ttl_sec=0
    )
    register_product_alpha_routes(app)

    response = app.test_client().get("/api/v1/market/snapshot")

    assert response.status_code == 200
    body = response.get_json()
    assert body["read_only"] is True
    assert body["execution_controls"] is False


def test_history_is_bounded_read_only_and_returns_candles():
    payload, status = PublicMarketHistoryService(adapter=_Adapter()).history(
        symbol="BTCUSDT", interval="15m", limit=9999
    )

    assert status == 200
    assert payload["read_only"] is True
    assert payload["execution_controls"] is False
    assert payload["limit"] == 120
    assert len(payload["candles"]) == 120
    assert payload["freshness"] == "FRESH"


def test_history_rejects_non_allowlisted_symbol_or_interval():
    service = PublicMarketHistoryService(adapter=_Adapter())
    assert service.history(symbol="SHIBUSDT", interval="15m", limit=60)[1] == 400
    assert service.history(symbol="BTCUSDT", interval="365d", limit=60)[1] == 400
