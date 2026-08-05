"""Synthetic / sanitized bar fixtures for V14-F regime lab (no live exchange)."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _checksum(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_bar(
    *,
    symbol: str,
    exchange_timestamp: int,
    receive_lag_ms: int = 1,
    close: float,
    volume_notional: float,
    funding_rate: float = 0.0,
    open_interest: float = 1_000_000.0,
    liquidation_notional: float = 0.0,
    seq: int = 0,
) -> dict[str, Any]:
    return {
        "schema": "v14_f_regime_bar_fixture",
        "symbol": symbol,
        "exchange_timestamp": int(exchange_timestamp),
        "receive_timestamp": int(exchange_timestamp) + int(receive_lag_ms),
        "close": float(close),
        "volume_notional": float(volume_notional),
        "funding_rate": float(funding_rate),
        "open_interest": float(open_interest),
        "liquidation_notional": float(liquidation_notional),
        "sequence_or_dedup_key": f"{symbol}:{seq}",
        "event_id": f"{symbol}:{exchange_timestamp}:{seq}",
        "capture_session_id": "synth_v14_f_regime_lab",
        "instrument_snapshot_id": "fixture_snap_v14_f",
    }


def build_synthetic_bars(
    *,
    seed: str = "v14f-default",
    base_ts_ms: int = 1_720_000_000_000,
    bar_ms: int = 60_000,
    n_bars: int = 40,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
) -> dict[str, Any]:
    """Deterministic multi-symbol OHLCV-style bars for regime + lead-lag proofs."""
    seed_n = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
    bars: list[dict[str, Any]] = []
    seq = 0
    for si, sym in enumerate(symbols):
        px0 = 100.0 + 50.0 * si + (seed_n % 23) * 0.01
        oi0 = 1_000_000.0 + 10_000.0 * si + (seed_n % 11) * 100.0
        for i in range(n_bars):
            ts = base_ts_ms + i * bar_ms
            # Mild trend + seed-dependent amplitude; ETH lags BTC slightly in returns.
            drift = 0.0004 * (1 if (seed_n + si) % 2 == 0 else -1)
            lead = 0.0
            if si == 1 and i >= 2:
                # ETH partially follows BTC move from 2 bars ago (descriptive fixture only).
                lead = 0.0003 * math.sin((i - 2) + seed_n % 7)
            shock = 0.0015 * math.sin(i * 0.7 + si + (seed_n % 5))
            px = px0 * (1.0 + drift * i + shock + lead)
            vol = 50_000.0 * (1.0 + 0.3 * abs(math.sin(i + si)) + 0.05 * (seed_n % 9))
            funding = 1e-5 * math.sin(i / 5.0 + si) + ((seed_n % 3) - 1) * 2e-6
            oi = oi0 * (1.0 + 0.002 * i * (1 if si == 0 else 0.5) + 0.001 * math.sin(i))
            liq = max(0.0, 5_000.0 * abs(shock) * (3.0 if abs(shock) > 0.0012 else 0.2))
            # One late-receive bar on primary symbol for NOT_YET_AVAILABLE / PIT tests.
            lag = 90_000 if (si == 0 and i == n_bars - 1) else 1
            bars.append(
                make_bar(
                    symbol=sym,
                    exchange_timestamp=ts,
                    receive_lag_ms=lag,
                    close=px,
                    volume_notional=vol,
                    funding_rate=funding,
                    open_interest=oi,
                    liquidation_notional=liq,
                    seq=seq,
                )
            )
            seq += 1

    lookback_end = base_ts_ms + (n_bars - 1) * bar_ms
    payload = {
        "schema": "v14_f_synthetic_bars",
        "seed": seed,
        "base_ts_ms": base_ts_ms,
        "bar_ms": bar_ms,
        "n_bars": n_bars,
        "symbols": list(symbols),
        "window_start_ms": base_ts_ms,
        "window_end_ms": lookback_end,
        "bars": bars,
        "bar_count": len(bars),
        "predictive_edge_claimed": False,
        "strategy_signal": False,
        "fixture_source": "synthetic_sanitized",
    }
    payload["fixture_checksum"] = _checksum(
        {k: v for k, v in payload.items() if k != "fixture_checksum"}
    )
    return payload
