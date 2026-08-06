"""Contract-only provider stubs — never fabricate LIVE values."""
from __future__ import annotations

from dataclasses import dataclass

from backend.nexus_official_market_adapters.constants import (
    CAPABILITIES,
    DATA_MODE_FIXTURE,
)
from backend.nexus_official_market_adapters.contracts import (
    AdapterManifest,
    OfficialReadOnlyMarketAdapter,
    assert_mode,
)
from backend.nexus_official_market_adapters.envelope import MarketObservation, unavailable


@dataclass
class ContractOnlyMarketAdapter(OfficialReadOnlyMarketAdapter):
    """Declares a provider contract without Live implementations."""

    adapter_id: str
    provider: str
    _mode: str = DATA_MODE_FIXTURE

    @property
    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            adapter_id=self.adapter_id,
            provider=self.provider,
            official=True,
            read_only=True,
            secret_required=False,
            account_endpoints=(),
            exchange_write_endpoints=(),
            public_rest_endpoints=(),
            public_ws_topics=(),
            capabilities=CAPABILITIES,
            supports_live_read_only=False,
            contract_only=True,
            notes=("contract_only — no Live reads; never fabricate LIVE_READ_ONLY payloads",),
        )

    def set_data_mode(self, mode: str) -> None:
        mode = assert_mode(mode)
        if mode != DATA_MODE_FIXTURE:
            raise ValueError(
                f"{self.adapter_id} is contract_only and cannot enter LIVE_READ_ONLY"
            )
        self._mode = mode

    def data_mode(self) -> str:
        return self._mode

    def capability_matrix(self) -> dict[str, str]:
        return {cap: "contract_only" for cap in CAPABILITIES}

    def _ua(self, capability: str, symbol: str | None = None) -> MarketObservation:
        return unavailable(
            capability=capability,
            adapter_id=self.adapter_id,
            provider=self.provider,
            reason="contract_only_no_live_implementation",
            data_mode=DATA_MODE_FIXTURE,
            symbol=symbol,
        )

    def fetch_instrument_catalog(self, *, category: str | None = None) -> MarketObservation:
        del category
        return self._ua("instrument_catalog")

    def fetch_ticker(self, *, symbol: str) -> MarketObservation:
        return self._ua("ticker", symbol)

    def fetch_mark_index_price(self, *, symbol: str) -> MarketObservation:
        return self._ua("mark_index_price", symbol)

    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        interval: str = "5m",
        limit: int = 10,
    ) -> MarketObservation:
        del interval, limit
        return self._ua("ohlcv", symbol)

    def fetch_public_trades(self, *, symbol: str, limit: int = 20) -> MarketObservation:
        del limit
        return self._ua("public_trades", symbol)

    def fetch_funding(self, *, symbol: str) -> MarketObservation:
        return self._ua("funding", symbol)

    def fetch_open_interest(self, *, symbol: str) -> MarketObservation:
        return self._ua("open_interest", symbol)

    def fetch_order_book_summary(self, *, symbol: str, depth: int = 25) -> MarketObservation:
        del depth
        return self._ua("order_book_summary", symbol)

    def fetch_liquidations(self, *, symbol: str, limit: int = 20) -> MarketObservation:
        del limit
        return self._ua("liquidation", symbol)

    def fetch_listing_status(self, *, symbol: str) -> MarketObservation:
        return self._ua("listing_status", symbol)

    def fetch_contract_specs(self, *, symbol: str) -> MarketObservation:
        return self._ua("contract_specs", symbol)


def build_contract_only_stubs() -> list[ContractOnlyMarketAdapter]:
    return [
        ContractOnlyMarketAdapter(adapter_id="okx_public", provider="okx"),
        ContractOnlyMarketAdapter(adapter_id="coinbase_exchange_public", provider="coinbase"),
        ContractOnlyMarketAdapter(adapter_id="kraken_public", provider="kraken"),
    ]


__all__ = ["ContractOnlyMarketAdapter", "build_contract_only_stubs"]
