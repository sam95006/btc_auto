"""Official read-only market adapter contracts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_official_market_adapters.constants import (
    CAPABILITIES,
    DATA_MODE_FIXTURE,
    DATA_MODE_LIVE_READ_ONLY,
)
from backend.nexus_official_market_adapters.envelope import MarketObservation


@dataclass(frozen=True)
class AdapterManifest:
    adapter_id: str
    provider: str
    official: bool
    read_only: bool
    secret_required: bool
    account_endpoints: tuple[str, ...]
    exchange_write_endpoints: tuple[str, ...]
    public_rest_endpoints: tuple[str, ...]
    public_ws_topics: tuple[str, ...]
    capabilities: tuple[str, ...]
    supports_live_read_only: bool
    contract_only: bool = False
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.secret_required:
            raise ValueError("official public adapters must not require secrets")
        if self.account_endpoints:
            raise ValueError("account endpoints forbidden on official read adapters")
        if self.exchange_write_endpoints:
            raise ValueError("exchange write endpoints forbidden on official read adapters")
        if not self.read_only:
            raise ValueError("adapters must be read_only")
        unknown = set(self.capabilities) - set(CAPABILITIES)
        if unknown:
            raise ValueError(f"unknown capabilities: {sorted(unknown)}")


class OfficialReadOnlyMarketAdapter(ABC):
    """Public market adapter — no keys, no account, no write."""

    @property
    @abstractmethod
    def manifest(self) -> AdapterManifest: ...

    @abstractmethod
    def set_data_mode(self, mode: str) -> None: ...

    @abstractmethod
    def data_mode(self) -> str: ...

    @abstractmethod
    def fetch_instrument_catalog(self, *, category: str | None = None) -> MarketObservation: ...

    @abstractmethod
    def fetch_ticker(self, *, symbol: str) -> MarketObservation: ...

    @abstractmethod
    def fetch_mark_index_price(self, *, symbol: str) -> MarketObservation: ...

    @abstractmethod
    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        interval: str = "5m",
        limit: int = 10,
    ) -> MarketObservation: ...

    @abstractmethod
    def fetch_public_trades(self, *, symbol: str, limit: int = 20) -> MarketObservation: ...

    @abstractmethod
    def fetch_funding(self, *, symbol: str) -> MarketObservation: ...

    @abstractmethod
    def fetch_open_interest(self, *, symbol: str) -> MarketObservation: ...

    @abstractmethod
    def fetch_order_book_summary(self, *, symbol: str, depth: int = 25) -> MarketObservation: ...

    @abstractmethod
    def fetch_liquidations(self, *, symbol: str, limit: int = 20) -> MarketObservation: ...

    @abstractmethod
    def fetch_listing_status(self, *, symbol: str) -> MarketObservation: ...

    @abstractmethod
    def fetch_contract_specs(self, *, symbol: str) -> MarketObservation: ...

    def stats(self) -> dict[str, Any]:
        return {}

    def capability_matrix(self) -> dict[str, str]:
        """Map capability -> support: live|fixture|unavailable|contract_only."""
        raise NotImplementedError


@dataclass
class CapabilitySupport:
    """Honest per-capability support declaration."""

    capability: str
    support: str  # implemented | contract_only | unavailable_legally | ws_only
    notes: str = ""


def assert_mode(mode: str) -> str:
    if mode not in {DATA_MODE_FIXTURE, DATA_MODE_LIVE_READ_ONLY}:
        raise ValueError(f"invalid data_mode: {mode}")
    return mode


__all__ = [
    "AdapterManifest",
    "OfficialReadOnlyMarketAdapter",
    "CapabilitySupport",
    "assert_mode",
]
