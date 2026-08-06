"""Read-only public market constitution — blocks secrets, account, and write paths."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from backend.nexus_official_market_adapters.constants import (
    ACCOUNT_PATH_MARKERS,
    BLOCKED_AUTH_HEADERS,
    HARD_BAN_SCRAPE_PROVIDERS,
    WRITE_METHODS,
)


class PublicMarketBoundaryError(RuntimeError):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"SECURITY_BLOCKED_PUBLIC_MARKET_BOUNDARY: {detail}")


@dataclass
class BoundaryCounters:
    account_endpoint_count: int = 0
    exchange_write_endpoint_count: int = 0
    secret_required_count: int = 0
    scrape_attempt_count: int = 0
    fabricated_live_value_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "account_endpoint_count": self.account_endpoint_count,
            "exchange_write_endpoint_count": self.exchange_write_endpoint_count,
            "secret_required_count": self.secret_required_count,
            "scrape_attempt_count": self.scrape_attempt_count,
            "fabricated_live_value_count": self.fabricated_live_value_count,
        }


@dataclass
class OfficialReadOnlyConstitution:
    """Enforces GET-only public market access for allowlisted hosts/paths."""

    allowlist_hosts: frozenset[str]
    allowlist_paths: frozenset[str]
    counters: BoundaryCounters = field(default_factory=BoundaryCounters)

    def validate_http_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, Any] | None = None,
    ) -> None:
        method_u = (method or "GET").upper()
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        path = parsed.path or "/"

        hdrs = {str(k).lower(): v for k, v in (headers or {}).items()}
        for blocked in BLOCKED_AUTH_HEADERS:
            if blocked in hdrs and hdrs[blocked]:
                self.counters.secret_required_count += 1
                raise PublicMarketBoundaryError(f"blocked auth/secret header: {blocked}")

        for banned in HARD_BAN_SCRAPE_PROVIDERS:
            if banned in host:
                self.counters.scrape_attempt_count += 1
                raise PublicMarketBoundaryError(f"blocked scrape/banned host: {banned}")

        if host and host not in self.allowlist_hosts:
            # Non-allowlisted hosts are rejected (no unauthorized data).
            raise PublicMarketBoundaryError(f"host not allowlisted: {host}")

        if method_u in WRITE_METHODS:
            self.counters.exchange_write_endpoint_count += 1
            raise PublicMarketBoundaryError(f"blocked write method {method_u}")

        if method_u != "GET":
            self.counters.exchange_write_endpoint_count += 1
            raise PublicMarketBoundaryError(f"blocked non-GET method {method_u}")

        normalized = path.rstrip("/") or "/"
        path_l = normalized.lower()
        for marker in ACCOUNT_PATH_MARKERS:
            if marker in path_l:
                self.counters.account_endpoint_count += 1
                raise PublicMarketBoundaryError(f"blocked account/private path: {normalized}")

        if normalized not in self.allowlist_paths:
            # Treat unknown market paths as private/unauthorized.
            self.counters.account_endpoint_count += 1
            raise PublicMarketBoundaryError(f"path not allowlisted: {normalized}")

    def record_fabricated_live_attempt(self) -> None:
        self.counters.fabricated_live_value_count += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "public_market_data_only": True,
            "allowlist_host_count": len(self.allowlist_hosts),
            "allowlist_path_count": len(self.allowlist_paths),
            "counters": self.counters.to_dict(),
        }


BYBIT_HOSTS = frozenset({"api.bybit.com", "api.bytick.com"})
BYBIT_PUBLIC_PATHS = frozenset(
    {
        "/v5/market/instruments-info",
        "/v5/market/tickers",
        "/v5/market/kline",
        "/v5/market/mark-price-kline",
        "/v5/market/index-price-kline",
        "/v5/market/orderbook",
        "/v5/market/recent-trade",
        "/v5/market/funding/history",
        "/v5/market/open-interest",
        # Bybit public REST has no dedicated historical liquidation list;
        # liquidations are WS-only — keep REST allowlist honest.
    }
)

BINANCE_USDM_HOSTS = frozenset({"fapi.binance.com"})
BINANCE_USDM_PUBLIC_PATHS = frozenset(
    {
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
    }
)


def bybit_constitution() -> OfficialReadOnlyConstitution:
    return OfficialReadOnlyConstitution(
        allowlist_hosts=BYBIT_HOSTS,
        allowlist_paths=BYBIT_PUBLIC_PATHS,
    )


def binance_usdm_constitution() -> OfficialReadOnlyConstitution:
    return OfficialReadOnlyConstitution(
        allowlist_hosts=BINANCE_USDM_HOSTS,
        allowlist_paths=BINANCE_USDM_PUBLIC_PATHS,
    )


__all__ = [
    "OfficialReadOnlyConstitution",
    "PublicMarketBoundaryError",
    "BoundaryCounters",
    "bybit_constitution",
    "binance_usdm_constitution",
    "BYBIT_HOSTS",
    "BYBIT_PUBLIC_PATHS",
    "BINANCE_USDM_HOSTS",
    "BINANCE_USDM_PUBLIC_PATHS",
]
