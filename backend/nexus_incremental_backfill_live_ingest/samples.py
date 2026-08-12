"""Bounded official / fixture / live-append samples for V18-B validation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.nexus_incremental_backfill_live_ingest.constants import (
    ALLOWED_BACKFILL_WINDOWS_DAYS,
    DATA_CLASS_FIXTURE,
    DATA_CLASS_LIVE_READ_ONLY,
    DATA_CLASS_OFFICIAL_HISTORICAL_SAMPLE,
    DEFAULT_LICENSE_REFERENCE,
    DEFAULT_SOURCE_ID,
    PRIORITY_SYMBOLS,
)
from backend.nexus_incremental_backfill_live_ingest.hashing import utc_now_iso


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kline_payload(*, symbol: str, open_px: str, idx: int, note: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "open": open_px,
        "high": str(float(open_px) * 1.001),
        "low": str(float(open_px) * 0.999),
        "close": str(float(open_px) * 1.0005),
        "volume": str(10 + idx),
        "interval": "1m",
        "sample_index": idx,
        "note": note,
    }


def fixture_batches() -> list[dict[str, Any]]:
    """Small synthetic fixtures for all priority symbols (not live network)."""
    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    prices = {"BTCUSDT": "42000.0", "ETHUSDT": "2300.0", "SOLUSDT": "98.0", "PEPEUSDT": "0.0000012"}
    out: list[dict[str, Any]] = []
    for i, sym in enumerate(PRIORITY_SYMBOLS):
        ts = base + timedelta(minutes=i)
        out.append(
            {
                "exchange_timestamp": _iso(ts),
                "received_timestamp": _iso(ts + timedelta(seconds=1)),
                "source_id": DEFAULT_SOURCE_ID,
                "symbol_original": sym,
                "data_class": DATA_CLASS_FIXTURE,
                "license_reference": DEFAULT_LICENSE_REFERENCE,
                "payload": _kline_payload(
                    symbol=sym, open_px=prices[sym], idx=i, note="fixture_priority_symbol"
                ),
            }
        )
    return out


def official_historical_sample_batches(*, window_days: int = 7) -> list[dict[str, Any]]:
    """Bounded official historical SAMPLE — not 15y / not all-exchange.

    Emits one sample bar per priority symbol anchored inside the allowed window.
    """
    if int(window_days) not in ALLOWED_BACKFILL_WINDOWS_DAYS:
        raise ValueError(f"backfill_window_refused:{window_days}")
    # Deterministic anchor inside a fixed sample epoch (not claiming live download).
    anchor = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    prices = {"BTCUSDT": "65000.0", "ETHUSDT": "3500.0", "SOLUSDT": "140.0", "PEPEUSDT": "0.000012"}
    out: list[dict[str, Any]] = []
    for i, sym in enumerate(PRIORITY_SYMBOLS):
        ts = anchor + timedelta(minutes=i)
        out.append(
            {
                "exchange_timestamp": _iso(ts),
                "received_timestamp": _iso(ts + timedelta(seconds=2)),
                "source_id": DEFAULT_SOURCE_ID,
                "symbol_original": sym,
                "data_class": DATA_CLASS_OFFICIAL_HISTORICAL_SAMPLE,
                "license_reference": "binance_public_api_tos_bounded_official_historical_sample",
                "payload": _kline_payload(
                    symbol=sym,
                    open_px=prices[sym],
                    idx=i,
                    note=f"official_historical_sample_window_{window_days}d",
                ),
                "backfill_window_days": int(window_days),
            }
        )
    return out


def live_append_batches(*, now: datetime | None = None) -> list[dict[str, Any]]:
    """LIVE_READ_ONLY append samples — shaped as public read-only ticks, no exchange write.

    Uses a frozen 'as_of' clock when provided so tests stay deterministic; default is utc now.
    """
    ref = now or datetime.now(timezone.utc)
    # Keep timestamps slightly in the past to avoid future-timestamp rejects under skew.
    base = ref - timedelta(seconds=5)
    prices = {"BTCUSDT": "67000.0", "ETHUSDT": "3600.0", "SOLUSDT": "150.0", "PEPEUSDT": "0.000013"}
    out: list[dict[str, Any]] = []
    for i, sym in enumerate(PRIORITY_SYMBOLS):
        ts = base - timedelta(seconds=len(PRIORITY_SYMBOLS) - i)
        out.append(
            {
                "exchange_timestamp": _iso(ts),
                "received_timestamp": utc_now_iso() if now is None else _iso(ts + timedelta(seconds=1)),
                "source_id": DEFAULT_SOURCE_ID,
                "symbol_original": sym,
                "data_class": DATA_CLASS_LIVE_READ_ONLY,
                "license_reference": "binance_public_api_tos_live_read_only_no_trade_write",
                "payload": _kline_payload(
                    symbol=sym, open_px=prices[sym], idx=i, note="live_read_only_append"
                ),
            }
        )
    return out


def instrument_observation(symbol: str) -> dict[str, Any]:
    """Minimal instrument observation for Silver identity bridge."""
    base = symbol.replace("USDT", "") if symbol.endswith("USDT") else symbol
    return {
        "exchange": "binance",
        "exchange_symbol": symbol,
        "market_type": "spot",
        "base_asset": base,
        "quote_asset": "USDT",
        "tick_size": 0.01 if symbol != "PEPEUSDT" else 0.00000001,
        "lot_size": 0.001,
        "min_notional": 5.0,
        "listing_time": "2020-01-01T00:00:00Z",
        "contract_rule_version": "v1",
    }


def sample_inventory() -> dict[str, Any]:
    f = fixture_batches()
    o = official_historical_sample_batches(window_days=7)
    # live samples are clock-dependent; count schema only
    return {
        "priority_symbols": list(PRIORITY_SYMBOLS),
        "priority_symbol_count": len(PRIORITY_SYMBOLS),
        "hard_max_symbols": False,
        "dynamic_universe_later": True,
        "fixture_count": len(f),
        "official_historical_sample_count": len(o),
        "allowed_backfill_windows_days": sorted(ALLOWED_BACKFILL_WINDOWS_DAYS),
        "claims_15y_complete": False,
        "claims_all_exchange_history": False,
        "claims_full_training_set": False,
        "claims_strategy_validation_pass": False,
        "generated_at": utc_now_iso(),
    }
