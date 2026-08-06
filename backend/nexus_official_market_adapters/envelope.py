"""Observation envelope — lineage, freshness, schema version; never fabricate."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_official_market_adapters.constants import (
    DATA_MODE_FIXTURE,
    DATA_MODE_LIVE_READ_ONLY,
    DATA_MODES,
    DEFAULT_FRESHNESS_STALE_MS,
    ENVELOPE_SCHEMA,
    QUALITY_DEGRADED,
    QUALITY_OK,
    QUALITY_STATES,
    QUALITY_STALE,
    QUALITY_UNAVAILABLE,
    SCHEMA_VERSION,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def safe_float(value: Any) -> float | None:
    """Parse float; never coerce missing/invalid to 0."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_freshness(
    *,
    exchange_timestamp_ms: int | None,
    received_at_ms: int,
    stale_after_ms: int = DEFAULT_FRESHNESS_STALE_MS,
) -> str:
    if exchange_timestamp_ms is None:
        return QUALITY_DEGRADED
    age = received_at_ms - int(exchange_timestamp_ms)
    if age < 0:
        # Clock skew — do not treat REST as always correct.
        return QUALITY_DEGRADED
    if age > stale_after_ms:
        return QUALITY_STALE
    return QUALITY_OK


@dataclass
class SourceLineage:
    provider: str
    adapter_id: str
    endpoint: str
    access_method: str  # official_rest_api | official_websocket | local_fixture
    host: str
    legal_basis: str = "official_public_market_api"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketObservation:
    """Normalized market observation with honesty metadata."""

    capability: str
    symbol: str | None
    payload: dict[str, Any] | list[Any] | None
    quality: str
    data_mode: str
    source_lineage: SourceLineage
    received_at_ms: int
    exchange_timestamp_ms: int | None = None
    schema: str = ENVELOPE_SCHEMA
    schema_version: int = SCHEMA_VERSION
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.quality not in QUALITY_STATES:
            raise ValueError(f"invalid quality: {self.quality}")
        if self.data_mode not in DATA_MODES:
            raise ValueError(f"invalid data_mode: {self.data_mode}")
        # Guard: never label fixture payloads as live.
        if self.data_mode == DATA_MODE_LIVE_READ_ONLY and self.source_lineage.access_method == "local_fixture":
            raise ValueError("FIXTURE access_method cannot be labeled LIVE_READ_ONLY")
        if self.data_mode == DATA_MODE_FIXTURE and self.source_lineage.access_method == "official_rest_api":
            # Allow only when explicitly fixture-backed mock of REST shape — force local_fixture.
            raise ValueError("FIXTURE mode requires access_method=local_fixture")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "capability": self.capability,
            "symbol": self.symbol,
            "payload": self.payload,
            "quality": self.quality,
            "data_mode": self.data_mode,
            "source_lineage": self.source_lineage.to_dict(),
            "received_at_ms": self.received_at_ms,
            "exchange_timestamp_ms": self.exchange_timestamp_ms,
            "notes": list(self.notes),
        }


def unavailable(
    *,
    capability: str,
    adapter_id: str,
    provider: str,
    reason: str,
    data_mode: str,
    symbol: str | None = None,
    endpoint: str = "",
    host: str = "",
) -> MarketObservation:
    access = "local_fixture" if data_mode == DATA_MODE_FIXTURE else "official_rest_api"
    # Contract-only / unavailable live must not fabricate values.
    if data_mode == DATA_MODE_LIVE_READ_ONLY and access == "official_rest_api" and not endpoint:
        access = "official_rest_api"
    return MarketObservation(
        capability=capability,
        symbol=symbol,
        payload=None,
        quality=QUALITY_UNAVAILABLE,
        data_mode=data_mode,
        source_lineage=SourceLineage(
            provider=provider,
            adapter_id=adapter_id,
            endpoint=endpoint or "n/a",
            access_method=access if data_mode == DATA_MODE_FIXTURE else "official_rest_api",
            host=host or "n/a",
            legal_basis="unavailable_or_not_implemented",
        ),
        received_at_ms=_now_ms(),
        exchange_timestamp_ms=None,
        notes=[reason],
    )


def wrap_ok(
    *,
    capability: str,
    adapter_id: str,
    provider: str,
    endpoint: str,
    host: str,
    payload: dict[str, Any] | list[Any],
    data_mode: str,
    exchange_timestamp_ms: int | None,
    symbol: str | None = None,
    access_method: str | None = None,
    notes: list[str] | None = None,
) -> MarketObservation:
    received = _now_ms()
    if access_method is None:
        access_method = "local_fixture" if data_mode == DATA_MODE_FIXTURE else "official_rest_api"
    quality = classify_freshness(
        exchange_timestamp_ms=exchange_timestamp_ms,
        received_at_ms=received,
    )
    if payload is None:
        quality = QUALITY_UNAVAILABLE
    return MarketObservation(
        capability=capability,
        symbol=symbol,
        payload=payload,
        quality=quality,
        data_mode=data_mode,
        source_lineage=SourceLineage(
            provider=provider,
            adapter_id=adapter_id,
            endpoint=endpoint,
            access_method=access_method,
            host=host,
        ),
        received_at_ms=received,
        exchange_timestamp_ms=exchange_timestamp_ms,
        notes=list(notes or []),
    )


__all__ = [
    "MarketObservation",
    "SourceLineage",
    "classify_freshness",
    "safe_float",
    "unavailable",
    "wrap_ok",
]
