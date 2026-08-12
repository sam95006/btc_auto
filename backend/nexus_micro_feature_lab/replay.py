"""Deterministic replay fingerprints for feature bundles."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_micro_feature_lab.extractors import extract_bundle_from_capture
from backend.nexus_micro_feature_lab.fixtures import build_synthetic_capture


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint_bundle(bundle: dict[str, Any]) -> str:
    # Fingerprint values + availability only (exclude non-deterministic wall clocks).
    payload = {
        "symbol": bundle.get("symbol"),
        "window_start_ms": bundle.get("window_start_ms"),
        "window_end_ms": bundle.get("window_end_ms"),
        "as_of_ms": bundle.get("as_of_ms"),
        "fixture_checksum": bundle.get("fixture_checksum"),
        "features": {
            fid: {
                "availability": obs.get("availability"),
                "value": obs.get("value"),
                "source_event_count": obs.get("source_event_count"),
                "event_timestamp_ms": obs.get("event_timestamp_ms"),
                "available_at_ms": obs.get("available_at_ms"),
                "missing_reason": obs.get("missing_reason"),
                "units": obs.get("units"),
            }
            for fid, obs in sorted((bundle.get("features") or {}).items())
        },
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def run_extraction_once(
    *,
    seed: str,
    symbol: str = "BTCUSDT",
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    capture = build_synthetic_capture(seed=seed)
    bundle = extract_bundle_from_capture(capture, symbol=symbol, as_of_ms=as_of_ms)
    fp = fingerprint_bundle(bundle)
    return {
        "seed": seed,
        "symbol": symbol,
        "as_of_ms": bundle["as_of_ms"],
        "fixture_checksum": capture["fixture_checksum"],
        "bundle": bundle,
        "fingerprint": fp,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "predictive_edge_claimed": False,
    }


def verify_deterministic_replay(
    *,
    seed: str,
    symbol: str = "BTCUSDT",
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    a = run_extraction_once(seed=seed, symbol=symbol, as_of_ms=as_of_ms)
    b = run_extraction_once(seed=seed, symbol=symbol, as_of_ms=as_of_ms)
    match = a["fingerprint"] == b["fingerprint"] and a["fixture_checksum"] == b["fixture_checksum"]
    return {
        "schema": "v13_e_deterministic_replay",
        "seed": seed,
        "symbol": symbol,
        "as_of_ms": a["as_of_ms"],
        "match": match,
        "fingerprint": a["fingerprint"],
        "fingerprint_b": b["fingerprint"],
        "fixture_checksum": a["fixture_checksum"],
        "feature_count": len(a["bundle"].get("features") or {}),
    }


def prove_pit_excludes_future(
    *,
    seed: str = "v13e-pit",
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    """Inject a future-dated trade; PIT as_of must ignore it."""
    capture = build_synthetic_capture(seed=seed)
    window_end = int(capture["window_end_ms"])
    as_of = window_end  # before late receive of last BTC trade (lag 50s) and before future inject
    # Choose as_of inside window but before the intentionally late receive on last BTC trade.
    # Late receive = last trade exchange_ts + 50000. Use mid-late as_of.
    base = int(capture["base_ts_ms"])
    as_of = base + 55_000  # within window; late receive at ~base+55000+50000 for last step

    baseline = extract_bundle_from_capture(capture, symbol=symbol, as_of_ms=as_of)
    future = {
        "schema": "microstructure_event_v13e_fixture",
        "family": "AGGRESSIVE_TRADE_FLOW",
        "event_id": "future_leak_probe",
        "exchange": "BYBIT",
        "symbol": symbol,
        "trade_id": "FUTURE",
        "exchange_timestamp": as_of + 10_000,
        "receive_timestamp": as_of + 10_001,
        "side": "BUY",
        "price": 999999.0,
        "quantity": 1000.0,
        "notional": 999999000.0,
        "aggressor_side_source": "FIXTURE",
        "sequence_or_dedup_key": f"{symbol}:FUTURE",
        "instrument_snapshot_id": "fixture_snap_v13e",
        "capture_session_id": "synth_v13e_feature_lab",
    }
    poisoned = dict(capture)
    poisoned["trades"] = list(capture["trades"]) + [future]
    after = extract_bundle_from_capture(poisoned, symbol=symbol, as_of_ms=as_of)
    fp_a = fingerprint_bundle(baseline)
    fp_b = fingerprint_bundle(after)
    return {
        "schema": "v13_e_pit_proof",
        "seed": seed,
        "symbol": symbol,
        "as_of_ms": as_of,
        "future_event_exchange_timestamp": future["exchange_timestamp"],
        "fingerprint_baseline": fp_a,
        "fingerprint_with_future": fp_b,
        "pit_holds": fp_a == fp_b,
        "predictive_edge_claimed": False,
    }
