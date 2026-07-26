"""Phase 6.6 — DemoDomainPolicy: hard allowlist for api-demo.bybit.com only."""
from __future__ import annotations

from urllib.parse import urlparse

from backend.nexus_research.demo_exchange.constants import (
    DEMO_REST_BASE_URL,
    DEMO_WS_PRIVATE_NOTE,
    FORBIDDEN_BASE_URLS,
    FORBIDDEN_WRITE_PATH_FRAGMENTS,
)
from backend.nexus_research.demo_exchange.errors import DomainRejectedError, MethodNotAllowedError, WriteForbiddenError


class DemoDomainPolicy:
    """Rejects mainnet, testnet, and arbitrary domains. GET-only enforcement helper."""

    ALLOWED_HOST = "api-demo.bybit.com"
    ALLOWED_SCHEME = "https"
    FUTURE_WS_NOTE = DEMO_WS_PRIVATE_NOTE  # do not enable WS trading

    def __init__(self, base_url: str = DEMO_REST_BASE_URL) -> None:
        self._base_url = self.validate_base_url(base_url)

    @property
    def base_url(self) -> str:
        return self._base_url

    @classmethod
    def validate_base_url(cls, url: str) -> str:
        raw = (url or "").strip().rstrip("/")
        if not raw:
            raise DomainRejectedError("empty_base_url")
        lowered = raw.lower()
        if lowered in {u.lower().rstrip("/") for u in FORBIDDEN_BASE_URLS}:
            raise DomainRejectedError(f"forbidden_base_url:{raw}")
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != cls.ALLOWED_SCHEME:
            raise DomainRejectedError(f"scheme_rejected:{parsed.scheme or 'none'}")
        if host != cls.ALLOWED_HOST:
            raise DomainRejectedError(f"host_rejected:{host or 'none'}")
        if host in {"api.bybit.com", "api-testnet.bybit.com"}:
            raise DomainRejectedError(f"host_rejected:{host}")
        return f"{cls.ALLOWED_SCHEME}://{cls.ALLOWED_HOST}"

    def assert_url_allowed(self, url: str) -> str:
        return self.validate_base_url(url)

    def assert_method_allowed(self, method: str) -> None:
        m = (method or "").upper().strip()
        if m != "GET":
            raise MethodNotAllowedError(f"method_not_allowed:{m or 'none'}")

    def assert_path_not_write(self, path: str) -> None:
        p = (path or "").lower()
        for frag in FORBIDDEN_WRITE_PATH_FRAGMENTS:
            if frag.lower() in p:
                raise WriteForbiddenError(f"write_path_forbidden:{frag}")

    def summary(self) -> dict:
        return {
            "allowedHost": self.ALLOWED_HOST,
            "allowedScheme": self.ALLOWED_SCHEME,
            "baseUrl": self._base_url,
            "wsTradingEnabled": False,
            "futureWsNote": self.FUTURE_WS_NOTE,
            "mainnetRejected": True,
            "testnetRejected": True,
            "arbitraryDomainRejected": True,
            "getOnly": True,
        }
