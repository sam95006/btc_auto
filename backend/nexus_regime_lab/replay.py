"""Deterministic replay fingerprints and PIT proofs for regime / lead-lag."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_regime_lab.fixtures import build_synthetic_bars, make_bar
from backend.nexus_regime_lab.lead_lag import lead_lag_from_capture, lead_lag_pair
from backend.nexus_regime_lab.regimes import classify_bundle_from_capture


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint_bundle(bundle: dict[str, Any]) -> str:
    payload = {
        "symbol": bundle.get("symbol"),
        "as_of_ms": bundle.get("as_of_ms"),
        "fixture_checksum": bundle.get("fixture_checksum"),
        "regimes": {
            rid: {
                "availability": obs.get("availability"),
                "label": obs.get("label"),
                "metrics": obs.get("metrics"),
                "source_bar_count": obs.get("source_bar_count"),
                "event_timestamp_ms": obs.get("event_timestamp_ms"),
                "available_at_ms": obs.get("available_at_ms"),
                "missing_reason": obs.get("missing_reason"),
            }
            for rid, obs in sorted((bundle.get("regimes") or {}).items())
        },
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def fingerprint_lead_lag(result: dict[str, Any]) -> str:
    payload = {
        "leader": result.get("leader"),
        "follower": result.get("follower"),
        "as_of_ms": result.get("as_of_ms"),
        "availability": result.get("availability"),
        "best_lag": result.get("best_lag"),
        "best_corr": result.get("best_corr"),
        "lags": {
            k: {"n_pairs": v.get("n_pairs"), "corr": v.get("corr")}
            for k, v in sorted((result.get("lags") or {}).items())
        },
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def run_classification_once(
    *,
    seed: str,
    symbol: str = "BTCUSDT",
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    capture = build_synthetic_bars(seed=seed)
    if as_of_ms is None:
        # Before late-receive on last BTC bar (90s lag).
        as_of_ms = int(capture["window_end_ms"]) + 1_000
    bundle = classify_bundle_from_capture(capture, symbol=symbol, as_of_ms=as_of_ms)
    ll = lead_lag_from_capture(capture, as_of_ms=as_of_ms)
    return {
        "seed": seed,
        "symbol": symbol,
        "as_of_ms": bundle["as_of_ms"],
        "fixture_checksum": capture["fixture_checksum"],
        "bundle": bundle,
        "lead_lag": ll,
        "fingerprint": fingerprint_bundle(bundle),
        "lead_lag_fingerprint": fingerprint_lead_lag(ll),
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
    a = run_classification_once(seed=seed, symbol=symbol, as_of_ms=as_of_ms)
    b = run_classification_once(seed=seed, symbol=symbol, as_of_ms=as_of_ms)
    match = (
        a["fingerprint"] == b["fingerprint"]
        and a["lead_lag_fingerprint"] == b["lead_lag_fingerprint"]
        and a["fixture_checksum"] == b["fixture_checksum"]
    )
    return {
        "schema": "v14_f_deterministic_replay",
        "seed": seed,
        "symbol": symbol,
        "as_of_ms": a["as_of_ms"],
        "match": match,
        "fingerprint": a["fingerprint"],
        "fingerprint_b": b["fingerprint"],
        "lead_lag_fingerprint": a["lead_lag_fingerprint"],
        "fixture_checksum": a["fixture_checksum"],
        "regime_count": len(a["bundle"].get("regimes") or {}),
    }


def prove_pit_excludes_future(
    *,
    seed: str = "v14f-pit",
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    """Inject a future-dated bar; PIT as_of must ignore it for regimes and lead-lag."""
    capture = build_synthetic_bars(seed=seed)
    base = int(capture["base_ts_ms"])
    # as_of inside window, before late receive on last bar.
    as_of = base + 20 * int(capture["bar_ms"])

    baseline = classify_bundle_from_capture(capture, symbol=symbol, as_of_ms=as_of)
    baseline_ll = lead_lag_from_capture(capture, as_of_ms=as_of)

    future = make_bar(
        symbol=symbol,
        exchange_timestamp=as_of + 10_000,
        receive_lag_ms=1,
        close=999999.0,
        volume_notional=9e12,
        funding_rate=0.5,
        open_interest=9e12,
        liquidation_notional=9e12,
        seq=999_999,
    )
    # Also poison peer for correlation / lead-lag leakage probe.
    future_eth = make_bar(
        symbol="ETHUSDT",
        exchange_timestamp=as_of + 10_000,
        receive_lag_ms=1,
        close=888888.0,
        volume_notional=9e12,
        funding_rate=0.5,
        open_interest=9e12,
        liquidation_notional=9e12,
        seq=999_998,
    )
    poisoned = dict(capture)
    poisoned["bars"] = list(capture["bars"]) + [future, future_eth]

    after = classify_bundle_from_capture(poisoned, symbol=symbol, as_of_ms=as_of)
    after_ll = lead_lag_from_capture(poisoned, as_of_ms=as_of)

    fp_a = fingerprint_bundle(baseline)
    fp_b = fingerprint_bundle(after)
    ll_a = fingerprint_lead_lag(baseline_ll)
    ll_b = fingerprint_lead_lag(after_ll)
    return {
        "schema": "v14_f_pit_proof",
        "seed": seed,
        "symbol": symbol,
        "as_of_ms": as_of,
        "future_bar_exchange_timestamp": future["exchange_timestamp"],
        "fingerprint_baseline": fp_a,
        "fingerprint_with_future": fp_b,
        "lead_lag_fingerprint_baseline": ll_a,
        "lead_lag_fingerprint_with_future": ll_b,
        "regime_pit_holds": fp_a == fp_b,
        "lead_lag_pit_holds": ll_a == ll_b,
        "pit_holds": fp_a == fp_b and ll_a == ll_b,
        "predictive_edge_claimed": False,
    }


def prove_lead_lag_no_negative_receive_leak(
    *,
    seed: str = "v14f-ll-pit",
) -> dict[str, Any]:
    """Bars with receive_timestamp > as_of must not enter lead-lag pairs."""
    capture = build_synthetic_bars(seed=seed)
    base = int(capture["base_ts_ms"])
    bar_ms = int(capture["bar_ms"])
    as_of = base + 15 * bar_ms
    # Inject bar with exchange_ts <= as_of but receive after as_of.
    leak = make_bar(
        symbol="BTCUSDT",
        exchange_timestamp=as_of - bar_ms,
        receive_lag_ms=120_000,
        close=123456.0,
        volume_notional=1e9,
        funding_rate=0.1,
        open_interest=1e9,
        liquidation_notional=1e9,
        seq=888_888,
    )
    baseline = lead_lag_pair(
        capture["bars"],
        leader="BTCUSDT",
        follower="ETHUSDT",
        as_of_ms=as_of,
        bar_ms=bar_ms,
    )
    poisoned_bars = list(capture["bars"]) + [leak]
    after = lead_lag_pair(
        poisoned_bars,
        leader="BTCUSDT",
        follower="ETHUSDT",
        as_of_ms=as_of,
        bar_ms=bar_ms,
    )
    holds = fingerprint_lead_lag(baseline) == fingerprint_lead_lag(after)
    return {
        "schema": "v14_f_lead_lag_receive_pit_proof",
        "as_of_ms": as_of,
        "injected_exchange_timestamp": leak["exchange_timestamp"],
        "injected_receive_timestamp": leak["receive_timestamp"],
        "pit_holds": holds,
        "predictive_edge_claimed": False,
        "trading_claim": False,
    }
