"""Adapter registry and acceptance counters for V18-A."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_official_market_adapters.binance.adapter import BinanceUsdmPublicAdapter
from backend.nexus_official_market_adapters.bybit.adapter import BybitPublicV5Adapter
from backend.nexus_official_market_adapters.constants import (
    DATA_MODE_FIXTURE,
    DATA_MODE_LIVE_READ_ONLY,
    HARD_BANS,
    OFFICIAL_READ_ADAPTER_IDS,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_official_market_adapters.contracts import OfficialReadOnlyMarketAdapter
from backend.nexus_official_market_adapters.stubs.contract_only import build_contract_only_stubs


@dataclass
class AcceptanceCounts:
    official_read_adapter_count: int = 0
    account_endpoint_count: int = 0
    exchange_write_endpoint_count: int = 0
    secret_required_count: int = 0
    fabricated_live_value_count: int = 0
    contract_only_provider_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "official_read_adapter_count": self.official_read_adapter_count,
            "account_endpoint_count": self.account_endpoint_count,
            "exchange_write_endpoint_count": self.exchange_write_endpoint_count,
            "secret_required_count": self.secret_required_count,
            "fabricated_live_value_count": self.fabricated_live_value_count,
            "contract_only_provider_count": self.contract_only_provider_count,
        }

    def passes(self) -> bool:
        return (
            self.official_read_adapter_count >= 2
            and self.account_endpoint_count == 0
            and self.exchange_write_endpoint_count == 0
            and self.secret_required_count == 0
            and self.fabricated_live_value_count == 0
        )


@dataclass
class OfficialMarketAdapterRegistry:
    use_fixtures: bool = True
    adapters: list[OfficialReadOnlyMarketAdapter] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.adapters:
            self.adapters = [
                BybitPublicV5Adapter(use_fixtures=self.use_fixtures),
                BinanceUsdmPublicAdapter(use_fixtures=self.use_fixtures),
                *build_contract_only_stubs(),
            ]

    def official_read_adapters(self) -> list[OfficialReadOnlyMarketAdapter]:
        return [a for a in self.adapters if a.manifest.official and not a.manifest.contract_only]

    def contract_only_adapters(self) -> list[OfficialReadOnlyMarketAdapter]:
        return [a for a in self.adapters if a.manifest.contract_only]

    def compute_acceptance(self) -> AcceptanceCounts:
        counts = AcceptanceCounts()
        for adapter in self.adapters:
            m = adapter.manifest
            if m.secret_required:
                counts.secret_required_count += 1
            counts.account_endpoint_count += len(m.account_endpoints)
            counts.exchange_write_endpoint_count += len(m.exchange_write_endpoints)
            if m.official and not m.contract_only and m.supports_live_read_only:
                counts.official_read_adapter_count += 1
            if m.contract_only:
                counts.contract_only_provider_count += 1
            # Probe constitution counters if present.
            stats = adapter.stats()
            constitution = stats.get("constitution") or {}
            c = constitution.get("counters") or {}
            counts.account_endpoint_count += int(c.get("account_endpoint_count") or 0)
            counts.exchange_write_endpoint_count += int(c.get("exchange_write_endpoint_count") or 0)
            counts.secret_required_count += int(c.get("secret_required_count") or 0)
            counts.fabricated_live_value_count += int(c.get("fabricated_live_value_count") or 0)

        # Detect fabricated Live: contract-only claiming LIVE_READ_ONLY payloads.
        for adapter in self.contract_only_adapters():
            try:
                adapter.set_data_mode(DATA_MODE_LIVE_READ_ONLY)
                counts.fabricated_live_value_count += 1
            except ValueError:
                pass
            # Ensure UNAVAILABLE and not zero-filled.
            obs = adapter.fetch_ticker(symbol="BTCUSDT")
            if obs.data_mode == DATA_MODE_LIVE_READ_ONLY:
                counts.fabricated_live_value_count += 1
            if obs.payload is not None and obs.quality != "UNAVAILABLE":
                # Contract-only must not emit live market values.
                counts.fabricated_live_value_count += 1

        # Official adapters must declare expected IDs.
        ids = {a.manifest.adapter_id for a in self.official_read_adapters()}
        if set(OFFICIAL_READ_ADAPTER_IDS) - ids:
            # Missing expected official adapters — do not inflate count.
            counts.official_read_adapter_count = min(
                counts.official_read_adapter_count,
                len(ids & set(OFFICIAL_READ_ADAPTER_IDS)),
            )
        return counts

    def smoke_fixture_capabilities(self, *, symbol: str = "BTCUSDT") -> dict[str, Any]:
        """Exercise all capabilities under FIXTURE mode; classify honestly."""
        results: dict[str, Any] = {}
        for adapter in self.official_read_adapters():
            adapter.set_data_mode(DATA_MODE_FIXTURE)
            aid = adapter.manifest.adapter_id
            # Use LINKUSDT for bybit fixtures, BTCUSDT for binance fixtures.
            sym = "LINKUSDT" if "bybit" in aid else symbol
            calls = {
                "instrument_catalog": adapter.fetch_instrument_catalog(),
                "ticker": adapter.fetch_ticker(symbol=sym),
                "mark_index_price": adapter.fetch_mark_index_price(symbol=sym),
                "ohlcv": adapter.fetch_ohlcv(symbol=sym),
                "public_trades": adapter.fetch_public_trades(symbol=sym),
                "funding": adapter.fetch_funding(symbol=sym),
                "open_interest": adapter.fetch_open_interest(symbol=sym),
                "order_book_summary": adapter.fetch_order_book_summary(symbol=sym),
                "liquidation": adapter.fetch_liquidations(symbol=sym),
                "listing_status": adapter.fetch_listing_status(symbol=sym),
                "contract_specs": adapter.fetch_contract_specs(symbol=sym),
            }
            results[aid] = {
                "data_mode": adapter.data_mode(),
                "capability_matrix": adapter.capability_matrix(),
                "observations": {
                    k: {
                        "quality": v.quality,
                        "data_mode": v.data_mode,
                        "payload_is_none": v.payload is None,
                        "access_method": v.source_lineage.access_method,
                        "has_received_at": v.received_at_ms is not None,
                        "schema_version": v.schema_version,
                    }
                    for k, v in calls.items()
                },
            }
        return results

    def evidence_summary(self) -> dict[str, Any]:
        counts = self.compute_acceptance()
        return {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "acceptance": counts.to_dict(),
            "acceptance_pass": counts.passes(),
            "hard_bans": list(HARD_BANS),
            "official_adapter_ids": [a.manifest.adapter_id for a in self.official_read_adapters()],
            "contract_only_ids": [a.manifest.adapter_id for a in self.contract_only_adapters()],
            "fixture_smoke": self.smoke_fixture_capabilities(),
        }


__all__ = [
    "AcceptanceCounts",
    "OfficialMarketAdapterRegistry",
]
