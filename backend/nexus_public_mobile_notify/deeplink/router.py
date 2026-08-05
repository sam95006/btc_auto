"""Deep-link routing for public mobile surfaces (PUB-K)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from backend.nexus_public_mobile_notify.constants import (
    DEEP_LINK_HOST,
    DEEP_LINK_ROUTES,
    DEEP_LINK_SCHEME,
)
from backend.nexus_public_mobile_notify.hard_bans import HardBanViolation, assert_no_private_fields

# Routes that must never be reachable from member deep links.
PRIVATE_ROUTE_DENYLIST = frozenset(
    {
        "founder",
        "private",
        "execution",
        "exchange",
        "wallet",
        "checkpoint",
        "lesson_memory",
        "reflection",
        "qualification_admin",
        "kill_switch",
    }
)


@dataclass(frozen=True)
class DeepLinkTarget:
    route: str
    params: dict[str, str]
    uri: str

    def to_dict(self) -> dict[str, Any]:
        d = {"route": self.route, "params": dict(self.params), "uri": self.uri}
        assert_no_private_fields(d)
        return d


class DeepLinkRouter:
    """Builds and parses `nexus://app/...` member deep links."""

    def __init__(
        self,
        *,
        scheme: str = DEEP_LINK_SCHEME,
        host: str = DEEP_LINK_HOST,
    ) -> None:
        self.scheme = scheme
        self.host = host

    def build(self, route: str, **params: str) -> DeepLinkTarget:
        if route not in DEEP_LINK_ROUTES:
            raise ValueError(f"unknown deep-link route: {route}")
        if route in PRIVATE_ROUTE_DENYLIST or any(p in PRIVATE_ROUTE_DENYLIST for p in params):
            raise HardBanViolation(f"HARD BAN: private deep-link route refused: {route}")
        assert_no_private_fields(params)
        query = urlencode({k: v for k, v in params.items() if v is not None})
        uri = f"{self.scheme}://{self.host}/{route}"
        if query:
            uri = f"{uri}?{query}"
        return DeepLinkTarget(route=route, params={k: str(v) for k, v in params.items()}, uri=uri)

    def parse(self, uri: str) -> DeepLinkTarget:
        parsed = urlparse(uri)
        if parsed.scheme != self.scheme or parsed.netloc != self.host:
            raise ValueError(f"unsupported deep-link URI: {uri}")
        route = parsed.path.lstrip("/").split("/")[0]
        if not route:
            raise ValueError("deep-link route missing")
        if route in PRIVATE_ROUTE_DENYLIST:
            raise HardBanViolation(f"HARD BAN: private deep-link route refused: {route}")
        if route not in DEEP_LINK_ROUTES:
            raise ValueError(f"unknown deep-link route: {route}")
        raw = parse_qs(parsed.query, keep_blank_values=False)
        params = {k: v[0] for k, v in raw.items()}
        assert_no_private_fields(params)
        return DeepLinkTarget(route=route, params=params, uri=uri)

    def for_alert(self, *, kind: str, decision_id: str | None = None) -> DeepLinkTarget:
        if kind == "DECISION_STATUS" and decision_id:
            return self.build("decision_detail", decision_id=decision_id)
        if kind == "RISK":
            if decision_id:
                return self.build("risks", decision_id=decision_id)
            return self.build("risks")
        if kind == "DATA_STALE":
            return self.build("alerts", focus="stale")
        if kind == "THESIS_INVALIDATED" and decision_id:
            return self.build("thesis_monitor", decision_id=decision_id)
        if kind == "MARKET_ANOMALY":
            return self.build("markets")
        return self.build("alerts")
