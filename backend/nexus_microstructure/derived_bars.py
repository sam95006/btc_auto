"""Deterministic derived aggregates from microstructure partitions (no signals)."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _window_key(ts_ms: int, window_ms: int) -> int:
    return (ts_ms // window_ms) * window_ms


def build_trade_bars(
    events: list[dict[str, Any]],
    *,
    window_ms: int,
    source_partition_checksum: str,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, int], dict[str, Any]] = {}
    for ev in events:
        ts = int(ev.get("exchange_timestamp") or 0)
        if ts <= 0:
            continue
        sym = str(ev.get("symbol") or "")
        key = (sym, _window_key(ts, window_ms))
        b = buckets.get(key)
        if b is None:
            b = {
                "symbol": sym,
                "window_start": key[1],
                "window_end": key[1] + window_ms,
                "buy_aggressor_notional": 0.0,
                "sell_aggressor_notional": 0.0,
                "net_aggressive_notional": 0.0,
                "trade_count": 0,
                "volume": 0.0,
                "notional_sum": 0.0,
                "record_count": 0,
                "missing_status": "OK",
                "schema_version": "microstructure_derived_bar_v1",
                "source_partition_checksums": [source_partition_checksum],
            }
            buckets[key] = b
        side = str(ev.get("side") or "UNKNOWN").upper()
        notional = float(ev.get("notional") or 0)
        qty = float(ev.get("quantity") or 0)
        b["trade_count"] += 1
        b["volume"] += qty
        b["notional_sum"] += notional
        b["record_count"] += 1
        if side == "BUY":
            b["buy_aggressor_notional"] += notional
        elif side == "SELL":
            b["sell_aggressor_notional"] += notional
        # UNKNOWN contributes to volume only
    out = []
    for b in buckets.values():
        b["net_aggressive_notional"] = b["buy_aggressor_notional"] - b["sell_aggressor_notional"]
        b["VWAP"] = (b["notional_sum"] / b["volume"]) if b["volume"] else None
        del b["notional_sum"]
        out.append(b)
    out.sort(key=lambda x: (x["symbol"], x["window_start"]))
    return out


def build_liquidation_bars(
    events: list[dict[str, Any]],
    *,
    window_ms: int,
    source_partition_checksum: str,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, int], dict[str, Any]] = {}
    for ev in events:
        ts = int(ev.get("exchange_timestamp") or 0)
        if ts <= 0:
            continue
        sym = str(ev.get("symbol") or "")
        key = (sym, _window_key(ts, window_ms))
        b = buckets.get(key)
        if b is None:
            b = {
                "symbol": sym,
                "window_start": key[1],
                "window_end": key[1] + window_ms,
                "long_liquidation_notional": 0.0,
                "short_liquidation_notional": 0.0,
                "liquidation_event_count": 0,
                "maximum_event_notional": 0.0,
                "record_count": 0,
                "missing_status": "OK",
                "schema_version": "microstructure_derived_bar_v1",
                "source_partition_checksums": [source_partition_checksum],
            }
            buckets[key] = b
        side = str(ev.get("liquidation_side") or "UNKNOWN").upper()
        notional = float(ev.get("notional") or 0)
        b["liquidation_event_count"] += 1
        b["record_count"] += 1
        b["maximum_event_notional"] = max(b["maximum_event_notional"], notional)
        # Bybit: Buy liquidation often means long liquidated (forced buy-to-cover depends on venue semantics)
        # Keep side as reported; map BUY->long_liq / SELL->short_liq without inventing.
        if side == "BUY":
            b["long_liquidation_notional"] += notional
        elif side == "SELL":
            b["short_liquidation_notional"] += notional
    out = list(buckets.values())
    out.sort(key=lambda x: (x["symbol"], x["window_start"]))
    return out


def validate_derived_bars(
    *,
    trade_events: list[dict[str, Any]],
    liq_events: list[dict[str, Any]],
    trade_checksum: str,
    liq_checksum: str,
) -> dict[str, Any]:
    bars_1s = build_trade_bars(trade_events, window_ms=1000, source_partition_checksum=trade_checksum)
    bars_5s = build_trade_bars(trade_events, window_ms=5000, source_partition_checksum=trade_checksum)
    bars_1m = build_trade_bars(trade_events, window_ms=60_000, source_partition_checksum=trade_checksum)
    liq_1m = build_liquidation_bars(liq_events, window_ms=60_000, source_partition_checksum=liq_checksum)
    linkage_ok = all(
        trade_checksum in (b.get("source_partition_checksums") or []) for b in bars_1s[:5]
    ) or len(bars_1s) == 0
    return {
        "schema": "derived_bar_validation",
        "derived_1s_bar_count": len(bars_1s),
        "derived_5s_bar_count": len(bars_5s),
        "derived_1m_bar_count": len(bars_1m),
        "liquidation_1m_bar_count": len(liq_1m),
        "source_checksum_linkage_status": "PASS" if linkage_ok else "FAIL",
        "signal_generated": False,
        "strategy_generated": False,
        "profitability_tested": False,
        "sample_1s_bar": bars_1s[0] if bars_1s else None,
    }
