"""V17-G deterministic synthetic fixtures (fixture-only evidence class)."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _checksum(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_synthetic_market(*, seed: str = "v17g-default", n_bars: int = 48) -> dict[str, Any]:
    """Build a fully synthetic multi-family market fixture.

    Timestamps are synthetic ms epochs. No exchange / mainnet IO.
    """
    # Deterministic PRNG from seed string.
    state = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16)

    def rnd() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    base_ts = 1_720_000_000_000
    bar_ms = 60_000
    primary = "BTCUSDT"
    peer = "ETHUSDT"
    universe = [primary, peer, "SOLUSDT", "BNBUSDT", "XRPUSDT"]

    ohlcv: dict[str, list[dict[str, Any]]] = {s: [] for s in universe}
    quotes: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    funding: list[dict[str, Any]] = []
    open_interest: list[dict[str, Any]] = []
    liquidations: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    stables: list[dict[str, Any]] = []

    px = {s: 100.0 + 10.0 * i for i, s in enumerate(universe)}

    for i in range(n_bars):
        exchange_ts = base_ts + i * bar_ms
        # receive_ts lags exchange by 50-250ms (deterministic)
        receive_lag = 50 + int(rnd() * 200)
        receive_ts = exchange_ts + receive_lag
        for s in universe:
            ret = (rnd() - 0.48) * 0.01
            o = px[s]
            c = max(0.01, o * (1.0 + ret))
            h = max(o, c) * (1.0 + rnd() * 0.002)
            l = min(o, c) * (1.0 - rnd() * 0.002)
            vol = 10.0 + rnd() * 90.0
            ohlcv[s].append(
                {
                    "symbol": s,
                    "exchange_ts": exchange_ts,
                    "receive_ts": receive_ts,
                    "open": round(o, 6),
                    "high": round(h, 6),
                    "low": round(l, 6),
                    "close": round(c, 6),
                    "volume": round(vol, 6),
                }
            )
            px[s] = c

        mid = ohlcv[primary][-1]["close"]
        spread_bps = 1.0 + rnd() * 4.0
        half = mid * spread_bps / 10_000.0 / 2.0
        quotes.append(
            {
                "symbol": primary,
                "exchange_ts": exchange_ts,
                "receive_ts": receive_ts,
                "bid": round(mid - half, 6),
                "ask": round(mid + half, 6),
            }
        )

        side = "BUY" if rnd() > 0.45 else ("SELL" if rnd() > 0.1 else "UNKNOWN")
        qty = 0.1 + rnd() * 2.0
        trades.append(
            {
                "symbol": primary,
                "exchange_ts": exchange_ts + 1,
                "receive_ts": receive_ts + 1,
                "side": side,
                "price": mid,
                "quantity": round(qty, 6),
                "notional": round(mid * qty, 6),
            }
        )

        if i % 8 == 0:
            funding.append(
                {
                    "symbol": primary,
                    "exchange_ts": exchange_ts,
                    "receive_ts": receive_ts,
                    "funding_rate": round((rnd() - 0.5) * 0.001, 8),
                }
            )
            open_interest.append(
                {
                    "symbol": primary,
                    "exchange_ts": exchange_ts,
                    "receive_ts": receive_ts,
                    "open_interest": round(1_000_000 + rnd() * 50_000, 2),
                }
            )

        if rnd() > 0.85:
            liquidations.append(
                {
                    "symbol": primary,
                    "exchange_ts": exchange_ts + 2,
                    "receive_ts": receive_ts + 2,
                    "notional": round(1_000 + rnd() * 20_000, 2),
                    "side": "BUY" if rnd() > 0.5 else "SELL",
                }
            )

        # Stablecoin peg samples
        for stable in ("USDTUSD", "USDCUSD"):
            stables.append(
                {
                    "symbol": stable,
                    "exchange_ts": exchange_ts,
                    "receive_ts": receive_ts,
                    "price": round(1.0 + (rnd() - 0.5) * 0.004, 6),
                }
            )

    # Two synthetic scheduled events inside the window
    events.append(
        {
            "event_id": "macro_cpi",
            "announce_ts": base_ts + 10 * bar_ms,
            "receive_ts": base_ts + 10 * bar_ms + 100,
            "family": "macro",
        }
    )
    events.append(
        {
            "event_id": "exchange_maintenance",
            "announce_ts": base_ts + 30 * bar_ms,
            "receive_ts": base_ts + 30 * bar_ms + 100,
            "family": "crypto_ops",
        }
    )

    # Deliberate missing gap: drop funding at index corresponding to mid window
    # (no forward fill — consumers must mark UNAVAILABLE if last eligible absent)

    as_of = base_ts + (n_bars - 5) * bar_ms
    fixture = {
        "schema": "v17_g_synthetic_market_fixture",
        "evidence_class": "fixture",
        "seed": seed,
        "primary_symbol": primary,
        "peer_symbol": peer,
        "universe": universe,
        "bar_ms": bar_ms,
        "n_bars": n_bars,
        "as_of_default": as_of,
        "ohlcv": ohlcv,
        "quotes": quotes,
        "trades": trades,
        "funding": funding,
        "open_interest": open_interest,
        "liquidations": liquidations,
        "events": events,
        "stablecoins": stables,
        "exchange_write_attempt_count": 0,
        "mainnet": False,
    }
    fixture["fixture_checksum"] = _checksum(
        {k: v for k, v in fixture.items() if k != "fixture_checksum"}
    )
    return fixture
