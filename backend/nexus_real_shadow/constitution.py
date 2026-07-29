"""Public market data boundary constitution — blocks private/authenticated exchange access."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse

BYBIT_HOST_PATTERN = re.compile(
    r"(^|\.)bybit\.(com|com\.cn|cloud)$",
    re.IGNORECASE,
)

PUBLIC_GET_PATH_ALLOWLIST = frozenset(
    {
        "/v5/market/instruments-info",
        "/v5/market/tickers",
        "/v5/market/kline",
        "/v5/market/orderbook",
        "/v5/market/funding/history",
        "/v5/market/open-interest",
        "/v5/market/mark-price-kline",
        "/v5/market/index-price-kline",
    }
)

PUBLIC_WS_TOPICS = frozenset(
    {
        "tickers",
        "orderbook.1",
        "orderbook.50",
        "kline.1",
        "kline.5",
        "publicTrade",
        "liquidation",
    }
)

BLOCKED_AUTH_HEADERS = frozenset(
    {
        "authorization",
        "x-bapi-api-key",
        "x-bapi-sign",
        "x-bapi-timestamp",
        "x-bapi-recv-window",
        "api-key",
        "api-sign",
        "api-timestamp",
        "api-signature",
    }
)

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class SecurityViolation(str, Enum):
    SECURITY_BLOCKED_PUBLIC_DATA_BOUNDARY = "SECURITY_BLOCKED_PUBLIC_DATA_BOUNDARY"


class PublicDataBoundaryError(RuntimeError):
    """Raised when a request violates the public market data boundary."""

    def __init__(self, detail: str, *, violation: SecurityViolation | None = None) -> None:
        self.detail = detail
        self.violation = violation or SecurityViolation.SECURITY_BLOCKED_PUBLIC_DATA_BOUNDARY
        super().__init__(f"{self.violation.value}: {detail}")


@dataclass
class ConstitutionCounters:
    private_endpoint_call_count: int = 0
    authenticated_request_count: int = 0
    exchange_write_call_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "private_endpoint_call_count": self.private_endpoint_call_count,
            "authenticated_request_count": self.authenticated_request_count,
            "exchange_write_call_count": self.exchange_write_call_count,
        }


@dataclass
class PublicMarketDataConstitution:
    """Enforces public GET-only access to Bybit market data endpoints."""

    allowlist_paths: frozenset[str] = PUBLIC_GET_PATH_ALLOWLIST
    allowlist_ws_topics: frozenset[str] = PUBLIC_WS_TOPICS
    counters: ConstitutionCounters = field(default_factory=ConstitutionCounters)

    def is_bybit_host(self, host: str) -> bool:
        return bool(BYBIT_HOST_PATTERN.search(host or ""))

    def validate_http_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, Any] | None = None,
    ) -> None:
        method_u = (method or "GET").upper()
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path.split("/")[0]
        path = parsed.path or "/"

        hdrs = {str(k).lower(): v for k, v in (headers or {}).items()}
        for blocked in BLOCKED_AUTH_HEADERS:
            if blocked in hdrs and hdrs[blocked]:
                self.counters.authenticated_request_count += 1
                raise PublicDataBoundaryError(
                    f"blocked auth header: {blocked}",
                    violation=SecurityViolation.SECURITY_BLOCKED_PUBLIC_DATA_BOUNDARY,
                )

        if not self.is_bybit_host(host):
            return

        if method_u in WRITE_METHODS:
            self.counters.exchange_write_call_count += 1
            raise PublicDataBoundaryError(
                f"blocked write method {method_u} to bybit",
                violation=SecurityViolation.SECURITY_BLOCKED_PUBLIC_DATA_BOUNDARY,
            )

        if method_u != "GET":
            self.counters.private_endpoint_call_count += 1
            raise PublicDataBoundaryError(
                f"blocked non-GET method {method_u}",
                violation=SecurityViolation.SECURITY_BLOCKED_PUBLIC_DATA_BOUNDARY,
            )

        normalized = path.rstrip("/") or "/"
        if normalized not in self.allowlist_paths:
            self.counters.private_endpoint_call_count += 1
            raise PublicDataBoundaryError(
                f"path not allowlisted: {normalized}",
                violation=SecurityViolation.SECURITY_BLOCKED_PUBLIC_DATA_BOUNDARY,
            )

    def validate_ws_topic(self, topic: str) -> None:
        base = (topic or "").split(".")[0]
        if topic not in self.allowlist_ws_topics and base not in self.allowlist_ws_topics:
            self.counters.private_endpoint_call_count += 1
            raise PublicDataBoundaryError(
                f"ws topic not allowlisted: {topic}",
                violation=SecurityViolation.SECURITY_BLOCKED_PUBLIC_DATA_BOUNDARY,
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "public_market_data_only": True,
            "allowlist_path_count": len(self.allowlist_paths),
            "allowlist_ws_topic_count": len(self.allowlist_ws_topics),
            "counters": self.counters.to_dict(),
        }
