"""Network egress traps — block authenticated writes and unexpected domains in CI."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator
from unittest.mock import patch
from urllib.parse import urlparse

from backend.nexus_autonomy.security_constants_v1 import (
    DEMO_HOST,
    FORBIDDEN_MAINNET_HOSTS,
    WRITE_PATH_FRAGMENTS,
)
from backend.nexus_autonomy.security_exceptions_v1 import NetworkEgressForbidden
from backend.nexus_autonomy.security_write_traps_v1 import path_is_exchange_write


ALLOWED_PUBLIC_READONLY_HOSTS: frozenset[str] = frozenset(
    {
        "api.bybit.com",  # public market data only (GET /v5/market/*)
    }
)


@dataclass
class NetworkEgressCounters:
    request_count: int = 0
    blocked_count: int = 0
    write_blocked_count: int = 0
    unexpected_domain_count: int = 0
    allowed_urls: list[str] = field(default_factory=list)
    blocked_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "blocked_count": self.blocked_count,
            "write_blocked_count": self.write_blocked_count,
            "unexpected_domain_count": self.unexpected_domain_count,
            "allowed_urls": list(self.allowed_urls),
            "blocked_urls": list(self.blocked_urls),
        }


def _check_url(
    url: str,
    *,
    counters: NetworkEgressCounters,
    allow_public_market: bool,
    allow_demo_host: bool,
) -> None:
    counters.request_count += 1
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    full = url

    if path_is_exchange_write(full) or any(f in path for f in WRITE_PATH_FRAGMENTS):
        counters.blocked_count += 1
        counters.write_blocked_count += 1
        counters.blocked_urls.append(full)
        raise NetworkEgressForbidden(full, "exchange_write_path")

    if host in FORBIDDEN_MAINNET_HOSTS and not (
        allow_public_market and path.startswith("/v5/market/")
    ):
        # Authenticated / non-market mainnet blocked
        if not path.startswith("/v5/market/"):
            counters.blocked_count += 1
            counters.unexpected_domain_count += 1
            counters.blocked_urls.append(full)
            raise NetworkEgressForbidden(full, "mainnet_non_market")

    if host == DEMO_HOST and not allow_demo_host:
        counters.blocked_count += 1
        counters.unexpected_domain_count += 1
        counters.blocked_urls.append(full)
        raise NetworkEgressForbidden(full, "demo_host_not_allowed_in_mode")

    if host and host not in ALLOWED_PUBLIC_READONLY_HOSTS and host != DEMO_HOST:
        # Unexpected third-party domain during trap mode
        counters.blocked_count += 1
        counters.unexpected_domain_count += 1
        counters.blocked_urls.append(full)
        raise NetworkEgressForbidden(full, "unexpected_domain")

    counters.allowed_urls.append(full)


@contextmanager
def network_egress_traps(
    *,
    allow_public_market: bool = True,
    allow_demo_host: bool = False,
) -> Iterator[NetworkEgressCounters]:
    """Monkeypatch urllib.request.urlopen to enforce egress policy."""
    counters = NetworkEgressCounters()
    import urllib.request as ureq

    real_urlopen = ureq.urlopen

    def _wrapped(req: Any = None, *args: Any, **kwargs: Any) -> Any:
        url = req
        if hasattr(req, "full_url"):
            url = req.full_url
        elif hasattr(req, "get_full_url"):
            url = req.get_full_url()
        _check_url(
            str(url),
            counters=counters,
            allow_public_market=allow_public_market,
            allow_demo_host=allow_demo_host,
        )
        # Never transmit in CI trap mode — raise after policy allow to keep zero real writes
        raise NetworkEgressForbidden(str(url), "trap_no_transmit")

    with patch.object(ureq, "urlopen", _wrapped):
        yield counters
    _ = real_urlopen
