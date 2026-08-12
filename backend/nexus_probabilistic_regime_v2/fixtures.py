"""Synthetic PIT fixtures for Probabilistic Regime Engine V2."""
from __future__ import annotations

import math
from typing import Any

from backend.nexus_probabilistic_regime_v2.constants import DEFAULT_BAR_MS, RANDOM_SEED


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def build_synthetic_bars(
    *,
    symbol: str = "BTCUSDT",
    n: int = 48,
    start_ms: int = 1_700_000_000_000,
    bar_ms: int = DEFAULT_BAR_MS,
    seed: int = RANDOM_SEED,
    scenario: str = "strong_bull",
    receive_lag_ms: int = 0,
) -> list[dict[str, Any]]:
    """Build deterministic exchange+receive timestamped bars for a scenario."""
    bars: list[dict[str, Any]] = []
    price = 60_000.0
    # Scenario drift / vol / liquidity knobs.
    knobs = {
        "strong_bull": dict(drift=0.0025, vol=0.004, spread=0.0002, depth=1.0, oi=0.4, funding=0.0001),
        "strong_bear": dict(drift=-0.0025, vol=0.004, spread=0.0002, depth=1.0, oi=0.4, funding=-0.0001),
        "vol_expansion": dict(drift=0.0, vol=0.035, spread=0.0008, depth=0.6, oi=0.7, funding=0.0003),
        "liquidity_stress": dict(drift=-0.0005, vol=0.01, spread=0.004, depth=0.1, oi=0.8, funding=0.0005),
        "long_crowding": dict(drift=0.001, vol=0.006, spread=0.0004, depth=0.7, oi=0.98, funding=0.0015),
        "corr_breakdown": dict(drift=0.0, vol=0.008, spread=0.0005, depth=0.8, oi=0.5, funding=0.0),
        "event_risk": dict(drift=-0.001, vol=0.015, spread=0.0015, depth=0.4, oi=0.85, funding=0.0008),
        "mixed": dict(drift=0.0002, vol=0.007, spread=0.0006, depth=0.55, oi=0.55, funding=0.0002),
        "stale": dict(drift=0.0, vol=0.005, spread=0.0004, depth=0.8, oi=0.5, funding=0.0),
        "unknown_thin": dict(drift=0.0, vol=0.001, spread=0.0001, depth=0.9, oi=0.2, funding=0.0),
    }
    k = knobs.get(scenario, knobs["mixed"])
    rng = seed
    for i in range(n):
        rng = (1103515245 * rng + 12345) & 0x7FFFFFFF
        shock = ((rng % 1000) / 1000.0 - 0.5) * 2.0 * k["vol"]
        # Alternating sign for mixed to create conflicting direction evidence.
        if scenario == "mixed" and i % 2 == 0:
            shock = abs(shock)
        elif scenario == "mixed":
            shock = -abs(shock)
        ret = k["drift"] + shock
        price = max(1.0, price * (1.0 + ret))
        ex = start_ms + i * bar_ms
        rx = ex + receive_lag_ms
        if scenario == "stale":
            # Receive lag grows so as_of near end sees stale data.
            rx = ex + receive_lag_ms + i * 15_000
        # Cross-asset proxy return (ETH) — high corr except corr_breakdown.
        if scenario == "corr_breakdown":
            peer_ret = -ret if i % 3 == 0 else ret * 0.1
        else:
            peer_ret = ret * 0.92 + shock * 0.05
        session_bucket = (ex // 3_600_000) % 24
        bars.append(
            {
                "symbol": symbol,
                "exchange_timestamp": ex,
                "receive_timestamp": rx,
                "open": price / (1.0 + ret),
                "high": price * (1.0 + abs(shock)),
                "low": price * (1.0 - abs(shock)),
                "close": price,
                "volume": 100.0 * k["depth"] * (1.0 + abs(shock) * 10),
                "spread_bps": k["spread"] * 10_000,
                "book_depth_score": k["depth"],
                "open_interest_z": k["oi"],
                "funding_rate": k["funding"],
                "peer_return": peer_ret,
                "own_return": ret,
                "liquidation_intensity": _clamp01(k["vol"] * 40 * (1.2 if scenario == "event_risk" else 0.5)),
                "net_capital_flow": k["drift"] * 1000,
                "microstructure_imbalance": _clamp01(0.5 + k["drift"] * 80),
                "event_flag": 1.0 if scenario == "event_risk" and i >= n - 6 else 0.0,
                "session_hour_utc": int(session_bucket),
                "scenario": scenario,
            }
        )
    return bars


def build_future_leak_bar(base_as_of_ms: int) -> dict[str, Any]:
    """Bar that must never be consumed under PIT as_of."""
    return {
        "symbol": "BTCUSDT",
        "exchange_timestamp": base_as_of_ms + 60_000,
        "receive_timestamp": base_as_of_ms + 60_500,
        "open": 61_000.0,
        "high": 61_100.0,
        "low": 60_900.0,
        "close": 61_050.0,
        "volume": 999.0,
        "spread_bps": 1.0,
        "book_depth_score": 1.0,
        "open_interest_z": 0.5,
        "funding_rate": 0.0,
        "peer_return": 0.01,
        "own_return": 0.01,
        "liquidation_intensity": 0.0,
        "net_capital_flow": 1.0,
        "microstructure_imbalance": 0.6,
        "event_flag": 0.0,
        "session_hour_utc": 12,
        "scenario": "future_leak",
    }


def log_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        a, b = closes[i - 1], closes[i]
        if a > 0 and b > 0:
            out.append(math.log(b / a))
    return out
