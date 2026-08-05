"""Synthetic / sanitized fixtures for V13-E feature lab (no live exchange)."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _event_id(symbol: str, family: str, ts_ms: int, seq: int) -> str:
    raw = f"{family}|{symbol}|{ts_ms}|{seq}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def make_trade(
    *,
    symbol: str,
    ts_ms: int,
    seq: int,
    side: str,
    price: float,
    quantity: float,
    receive_lag_ms: int = 1,
    capture_session_id: str = "synth_v13e_feature_lab",
) -> dict[str, Any]:
    notional = float(price) * float(quantity)
    return {
        "schema": "microstructure_event_v13e_fixture",
        "family": "AGGRESSIVE_TRADE_FLOW",
        "event_id": _event_id(symbol, "AGGRESSIVE_TRADE_FLOW", ts_ms, seq),
        "exchange": "BYBIT",
        "symbol": symbol,
        "trade_id": f"T{seq}",
        "exchange_timestamp": int(ts_ms),
        "receive_timestamp": int(ts_ms) + int(receive_lag_ms),
        "side": side,
        "price": float(price),
        "quantity": float(quantity),
        "notional": notional,
        "aggressor_side_source": "FIXTURE",
        "sequence_or_dedup_key": f"{symbol}:{seq}",
        "instrument_snapshot_id": "fixture_snap_v13e",
        "capture_session_id": capture_session_id,
    }


def make_liquidation(
    *,
    symbol: str,
    ts_ms: int,
    seq: int,
    side: str,
    price: float,
    quantity: float,
    receive_lag_ms: int = 1,
    capture_session_id: str = "synth_v13e_feature_lab",
) -> dict[str, Any]:
    notional = float(price) * float(quantity)
    return {
        "schema": "microstructure_event_v13e_fixture",
        "family": "LIQUIDATION_EVENTS",
        "event_id": _event_id(symbol, "LIQUIDATION_EVENTS", ts_ms, seq),
        "exchange": "BYBIT",
        "symbol": symbol,
        "exchange_timestamp": int(ts_ms),
        "receive_timestamp": int(ts_ms) + int(receive_lag_ms),
        "liquidation_side": side,
        "price": float(price),
        "quantity": float(quantity),
        "notional": notional,
        "event_source": "FIXTURE",
        "sequence_or_dedup_key": f"{symbol}:L{seq}",
        "instrument_snapshot_id": "fixture_snap_v13e",
        "capture_session_id": capture_session_id,
    }


def build_synthetic_capture(
    *,
    seed: str = "v13e-default",
    base_ts_ms: int = 1_720_000_000_000,
    window_ms: int = 60_000,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
) -> dict[str, Any]:
    """Deterministic multi-symbol trade + liquidation fixture for one parent window."""
    # Seed only influences amplitude via hash — no RNG object (fully deterministic).
    seed_n = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
    trades: list[dict[str, Any]] = []
    liqs: list[dict[str, Any]] = []
    seq = 0
    # 12 ticks across the window
    steps = 12
    step = window_ms // steps
    for si, sym in enumerate(symbols):
        px0 = 100.0 + 10.0 * si + (seed_n % 17) * 0.01
        for i in range(steps):
            ts = base_ts_ms + i * step + si  # slight symbol offset, still in window
            # Alternating but with persistence bias for first half
            if i < steps // 2:
                side = "BUY" if (i + si) % 3 != 0 else "SELL"
            else:
                side = "SELL" if (i + si) % 3 != 0 else "BUY"
            qty = 0.01 * (1 + (i + si + seed_n % 5) % 7)
            px = px0 * (1.0 + 0.0005 * math.sin(i + si) + 0.0002 * (1 if side == "BUY" else -1))
            # One late-receive event for PIT / availability tests
            lag = 50_000 if (si == 0 and i == steps - 1) else 1
            trades.append(
                make_trade(
                    symbol=sym,
                    ts_ms=ts,
                    seq=seq,
                    side=side,
                    price=px,
                    quantity=qty,
                    receive_lag_ms=lag,
                )
            )
            seq += 1
            if i % 4 == 0:
                # Cluster liquidations near start of window for primary symbol
                cluster_ts = base_ts_ms + (200 if si == 0 else i * step)
                liqs.append(
                    make_liquidation(
                        symbol=sym,
                        ts_ms=cluster_ts + (seq % 3) * 100,
                        seq=seq,
                        side="SELL" if side == "BUY" else "BUY",
                        price=px,
                        quantity=qty * 2,
                    )
                )
                seq += 1
        # One UNKNOWN aggressor (must not invent side)
        trades.append(
            make_trade(
                symbol=sym,
                ts_ms=base_ts_ms + window_ms // 2 + 7 + si,
                seq=seq,
                side="UNKNOWN",
                price=px0,
                quantity=0.05,
            )
        )
        seq += 1

    payload = {
        "schema": "v13_e_synthetic_capture",
        "seed": seed,
        "base_ts_ms": base_ts_ms,
        "window_ms": window_ms,
        "window_start_ms": base_ts_ms,
        "window_end_ms": base_ts_ms + window_ms,
        "symbols": list(symbols),
        "trades": trades,
        "liquidations": liqs,
        "trade_count": len(trades),
        "liquidation_count": len(liqs),
        "predictive_edge_claimed": False,
    }
    payload["fixture_checksum"] = hashlib.sha256(
        json.dumps(
            {
                "seed": seed,
                "base_ts_ms": base_ts_ms,
                "window_ms": window_ms,
                "symbols": list(symbols),
                "trade_ids": [t["event_id"] for t in trades],
                "liq_ids": [x["event_id"] for x in liqs],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return payload
