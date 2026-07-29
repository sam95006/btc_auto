"""Dynamic instrument discovery and metadata store."""
from __future__ import annotations

from typing import Any

from backend.nexus_real_shadow.instruments import (
    BybitPublicInstrumentProvider,
    DynamicInstrumentDiscoveryWorker,
    UniverseDiscoverySnapshot,
    UniverseFunnelCounts,
    load_fixture,
    parse_instruments_info,
)

__all__ = [
    "BybitPublicInstrumentProvider",
    "DynamicInstrumentDiscoveryWorker",
    "InstrumentMetadataStore",
    "UniverseDiscoverySnapshot",
    "UniverseFunnelCounts",
    "load_fixture",
    "parse_instruments_info",
]


class InstrumentMetadataStore:
    """In-memory store for discovered USDT linear perpetual instrument metadata."""

    def __init__(self) -> None:
        self._by_symbol: dict[str, dict[str, Any]] = {}

    def upsert_many(self, instruments: list[dict[str, Any]]) -> int:
        count = 0
        for row in instruments:
            sym = str(row.get("symbol") or "")
            if sym:
                self._by_symbol[sym] = dict(row)
                count += 1
        return count

    def get(self, symbol: str) -> dict[str, Any] | None:
        return self._by_symbol.get(symbol)

    def all(self) -> list[dict[str, Any]]:
        return list(self._by_symbol.values())

    def symbols(self) -> list[str]:
        return list(self._by_symbol.keys())

    def count(self) -> int:
        return len(self._by_symbol)

    def clear(self) -> None:
        self._by_symbol.clear()
