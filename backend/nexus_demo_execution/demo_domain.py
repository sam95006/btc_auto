"""Demo-only API domain allowlist — blocks mainnet and testnet endpoints."""
from __future__ import annotations

from urllib.parse import urlparse

DEMO_REST_BASE_URL = "https://api-demo.bybit.com"
ALLOWED_HOST = "api-demo.bybit.com"
ALLOWED_SCHEME = "https"

FORBIDDEN_BASE_URLS = frozenset(
    {
        "https://api.bybit.com",
        "http://api.bybit.com",
        "https://api-testnet.bybit.com",
        "http://api-testnet.bybit.com",
        "https://www.bybit.com",
        "http://www.bybit.com",
    }
)

FORBIDDEN_HOSTS = frozenset(
    {
        "api.bybit.com",
        "api-testnet.bybit.com",
        "www.bybit.com",
    }
)


class DemoDomainRejectedError(RuntimeError):
    """Raised when a URL violates demo-only domain policy."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


class DemoDomainPolicy:
    """Hard allowlist for api-demo.bybit.com only."""

    def __init__(self, base_url: str = DEMO_REST_BASE_URL) -> None:
        self._base_url = self.validate_base_url(base_url)

    @property
    def base_url(self) -> str:
        return self._base_url

    @classmethod
    def validate_base_url(cls, url: str) -> str:
        raw = (url or "").strip().rstrip("/")
        if not raw:
            raise DemoDomainRejectedError("empty_base_url")
        lowered = raw.lower()
        if lowered in {u.lower().rstrip("/") for u in FORBIDDEN_BASE_URLS}:
            raise DemoDomainRejectedError("mainnet_or_testnet_forbidden", raw)
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != ALLOWED_SCHEME:
            raise DemoDomainRejectedError("scheme_rejected", parsed.scheme or "none")
        if host in FORBIDDEN_HOSTS:
            raise DemoDomainRejectedError("forbidden_host", host)
        if host != ALLOWED_HOST:
            raise DemoDomainRejectedError("host_rejected", host or "none")
        return f"{ALLOWED_SCHEME}://{ALLOWED_HOST}"

    def assert_url_allowed(self, url: str) -> str:
        return self.validate_base_url(url)

    def is_mainnet_url(self, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return True
        return host in FORBIDDEN_HOSTS or "api.bybit.com" in host and host != ALLOWED_HOST

    def summary(self) -> dict:
        return {
            "allowedHost": ALLOWED_HOST,
            "allowedScheme": ALLOWED_SCHEME,
            "baseUrl": self._base_url,
            "mainnetRejected": True,
            "testnetRejected": True,
            "arbitraryDomainRejected": True,
            "bybitDemoOnly": True,
        }
