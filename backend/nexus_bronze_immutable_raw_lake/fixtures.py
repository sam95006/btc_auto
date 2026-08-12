"""Bounded fixture / small official sample ONLY — no 15y history claim."""
from __future__ import annotations

from typing import Any

from backend.nexus_bronze_immutable_raw_lake.constants import (
    CLASSIFICATION_BOUNDED_OFFICIAL_SAMPLE,
    CLASSIFICATION_FIXTURE,
    DEFAULT_LICENSE_REFERENCE,
)


# Tiny synthetic kline-like samples (fixture). Not live exchange download.
_FIXTURE_SAMPLES: tuple[dict[str, Any], ...] = (
    {
        "exchange_timestamp": "2024-01-01T00:00:00Z",
        "received_timestamp": "2024-01-01T00:00:01Z",
        "source_id": "fixture.binance.spot.kline.1m",
        "symbol_original": "BTCUSDT",
        "classification": CLASSIFICATION_FIXTURE,
        "license_reference": DEFAULT_LICENSE_REFERENCE,
        "payload": {
            "open": "42000.0",
            "high": "42100.0",
            "low": "41950.0",
            "close": "42050.0",
            "volume": "12.5",
            "interval": "1m",
            "sample_index": 0,
        },
    },
    {
        "exchange_timestamp": "2024-01-01T00:01:00Z",
        "received_timestamp": "2024-01-01T00:01:01Z",
        "source_id": "fixture.binance.spot.kline.1m",
        "symbol_original": "BTCUSDT",
        "classification": CLASSIFICATION_FIXTURE,
        "license_reference": DEFAULT_LICENSE_REFERENCE,
        "payload": {
            "open": "42050.0",
            "high": "42080.0",
            "low": "42010.0",
            "close": "42020.0",
            "volume": "8.1",
            "interval": "1m",
            "sample_index": 1,
        },
    },
    {
        "exchange_timestamp": "2024-01-01T00:02:00Z",
        "received_timestamp": "2024-01-01T00:02:01Z",
        "source_id": "fixture.binance.spot.kline.1m",
        "symbol_original": "BTCUSDT",
        "classification": CLASSIFICATION_FIXTURE,
        "license_reference": DEFAULT_LICENSE_REFERENCE,
        "payload": {
            "open": "42020.0",
            "high": "42040.0",
            "low": "41990.0",
            "close": "42000.0",
            "volume": "5.4",
            "interval": "1m",
            "sample_index": 2,
        },
    },
)

# One bounded "official sample" shaped like a public REST snippet — still not full history.
_OFFICIAL_SAMPLE: dict[str, Any] = {
    "exchange_timestamp": "2024-06-15T12:00:00Z",
    "received_timestamp": "2024-06-15T12:00:02Z",
    "source_id": "official_sample.binance.public.rest.kline",
    "symbol_original": "ETHUSDT",
    "classification": CLASSIFICATION_BOUNDED_OFFICIAL_SAMPLE,
    "license_reference": "binance_public_api_terms_sample_snippet_not_redistributed_bulk",
    "payload": {
        "open": "3500.0",
        "high": "3505.0",
        "low": "3498.0",
        "close": "3502.0",
        "volume": "100.0",
        "interval": "1m",
        "note": "bounded_official_sample_n1",
    },
}


def bounded_fixture_samples() -> list[dict[str, Any]]:
    """Return a shallow copy of the bounded fixture set (N=3)."""
    return [dict(s) for s in _FIXTURE_SAMPLES]


def bounded_official_samples() -> list[dict[str, Any]]:
    """Return the single bounded official sample — NOT a multi-year download."""
    return [dict(_OFFICIAL_SAMPLE)]


def all_bounded_ingest_batches() -> list[dict[str, Any]]:
    return bounded_fixture_samples() + bounded_official_samples()


def sample_inventory() -> dict[str, Any]:
    batches = all_bounded_ingest_batches()
    return {
        "fixture_count": len(bounded_fixture_samples()),
        "official_sample_count": len(bounded_official_samples()),
        "total_bounded_samples": len(batches),
        "claims_15y_history_downloaded": False,
        "classification_set": sorted({b["classification"] for b in batches}),
        "symbols": sorted({b["symbol_original"] for b in batches}),
        "source_ids": sorted({b["source_id"] for b in batches}),
    }
