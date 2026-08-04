"""Microstructure V1.1 integrity helpers: clock, latency, symbol-scoped ordering."""
from __future__ import annotations

import json
import statistics
import time
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

BYBIT_SERVER_TIME = "https://api.bybit.com/v5/market/time"


def utc_ms() -> int:
    return int(time.time() * 1000)


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return float(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


def sample_bybit_clock_offset() -> dict[str, Any]:
    """Estimate local_wall - server_time using Bybit public /v5/market/time."""
    t0 = utc_ms()
    with urllib.request.urlopen(BYBIT_SERVER_TIME, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    t1 = utc_ms()
    result = payload.get("result") or {}
    # Bybit returns timeSecond and/or timeNano
    server_ms = None
    if result.get("timeNano"):
        server_ms = int(int(result["timeNano"]) / 1_000_000)
    elif result.get("timeSecond"):
        server_ms = int(result["timeSecond"]) * 1000
    elif payload.get("time"):
        server_ms = int(payload["time"])
    mid = (t0 + t1) // 2
    offset = None if server_ms is None else mid - server_ms
    return {
        "local_request_ms": t0,
        "local_response_ms": t1,
        "server_ms": server_ms,
        "local_minus_server_clock_offset_ms": offset,
        "rtt_ms": t1 - t0,
    }


@dataclass
class ClockTracker:
    samples: list[dict[str, Any]] = field(default_factory=list)

    def sample(self) -> dict[str, Any]:
        s = sample_bybit_clock_offset()
        self.samples.append(s)
        return s

    def current_offset_ms(self) -> float | None:
        vals = [
            float(s["local_minus_server_clock_offset_ms"])
            for s in self.samples
            if s.get("local_minus_server_clock_offset_ms") is not None
        ]
        if not vals:
            return None
        return float(statistics.median(vals))

    def report(self) -> dict[str, Any]:
        vals = sorted(
            float(s["local_minus_server_clock_offset_ms"])
            for s in self.samples
            if s.get("local_minus_server_clock_offset_ms") is not None
        )
        return {
            "server_clock_sample_count": len(vals),
            "local_minus_server_clock_offset_ms_min": vals[0] if vals else None,
            "local_minus_server_clock_offset_ms_p50": percentile(vals, 50),
            "local_minus_server_clock_offset_ms_p95": percentile(vals, 95),
            "local_minus_server_clock_offset_ms_max": vals[-1] if vals else None,
        }


@dataclass
class SymbolOrderingTracker:
    """Per-symbol exchange-timestamp ordering (never cross-symbol)."""

    last_exchange_ts: dict[tuple[str, str, str], int] = field(default_factory=dict)
    per_symbol_out_of_order_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    per_symbol_max_backward_ms: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    per_symbol_event_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    session_out_of_order_count: int = 0

    def observe(self, *, exchange: str, family: str, symbol: str, topic: str, exchange_ts: int) -> None:
        if exchange_ts <= 0:
            return
        key = (exchange, family, symbol)
        self.per_symbol_event_count[symbol] += 1
        prev = self.last_exchange_ts.get(key)
        if prev is not None and exchange_ts < prev:
            back = prev - exchange_ts
            self.per_symbol_out_of_order_count[symbol] += 1
            self.session_out_of_order_count += 1
            if back > self.per_symbol_max_backward_ms[symbol]:
                self.per_symbol_max_backward_ms[symbol] = back
        if prev is None or exchange_ts >= prev:
            self.last_exchange_ts[key] = exchange_ts

    def report(self) -> dict[str, Any]:
        ooo_symbols = [s for s, n in self.per_symbol_out_of_order_count.items() if n > 0]
        total = sum(self.per_symbol_event_count.values()) or 0
        return {
            "per_symbol_out_of_order_count": dict(self.per_symbol_out_of_order_count),
            "per_symbol_max_backward_ms": dict(self.per_symbol_max_backward_ms),
            "per_symbol_event_count": dict(self.per_symbol_event_count),
            "session_out_of_order_count": self.session_out_of_order_count,
            "out_of_order_symbol_count": len(ooo_symbols),
            "out_of_order_ratio": (self.session_out_of_order_count / total) if total else 0.0,
            "maximum_backward_ms": max(self.per_symbol_max_backward_ms.values()) if self.per_symbol_max_backward_ms else 0,
            "sequence_gap_status": "UNKNOWN",
            "documented_sequence_available": False,
            "sequence_gap_count": 0,
            "unknown_gap_interval_count": 0,
            "note": "Trade/liquidation quiet intervals are not inferred as market gaps",
        }


@dataclass
class LatencyTracker:
    raw: list[float] = field(default_factory=list)
    corrected: list[float] = field(default_factory=list)
    negative_raw_latency_count: int = 0
    negative_corrected_latency_count: int = 0
    by_family_symbol: dict[tuple[str, str], dict[str, list[float]]] = field(
        default_factory=lambda: defaultdict(lambda: {"raw": [], "corrected": []})
    )

    def observe(
        self,
        *,
        family: str,
        symbol: str,
        exchange_ts: int,
        receive_wall_ts: int,
        clock_offset_ms: float | None,
    ) -> dict[str, Any]:
        raw = float(receive_wall_ts - exchange_ts) if exchange_ts else None
        corrected = None
        if raw is not None and clock_offset_ms is not None:
            # receive_local ≈ exchange_server + latency + offset(local-server)
            # corrected_latency ≈ raw - offset
            corrected = raw - float(clock_offset_ms)
        neg_raw = bool(raw is not None and raw < 0)
        neg_corr = bool(corrected is not None and corrected < 0)
        if neg_raw:
            self.negative_raw_latency_count += 1
        if neg_corr:
            self.negative_corrected_latency_count += 1
        if raw is not None:
            self.raw.append(raw)
            self.by_family_symbol[(family, symbol)]["raw"].append(raw)
        if corrected is not None:
            self.corrected.append(corrected)
            self.by_family_symbol[(family, symbol)]["corrected"].append(corrected)
        return {
            "raw_receive_minus_exchange_ms": raw,
            "clock_corrected_latency_ms": corrected,
            "negative_raw_latency_flag": neg_raw,
            "latency_quality_status": (
                "NEGATIVE_RAW"
                if neg_raw
                else ("NEGATIVE_CORRECTED" if neg_corr else ("OK" if corrected is not None else "OFFSET_UNKNOWN"))
            ),
        }

    def _lat_report(self, vals: list[float]) -> dict[str, Any]:
        s = sorted(vals)
        return {
            "raw_latency_min_ms": s[0] if s else None,
            "raw_latency_p50_ms": percentile(s, 50),
            "raw_latency_p95_ms": percentile(s, 95),
            "raw_latency_p99_ms": percentile(s, 99),
            "raw_latency_max_ms": s[-1] if s else None,
        }

    def report(self) -> dict[str, Any]:
        raw_s = sorted(self.raw)
        corr_s = sorted(self.corrected)
        return {
            "raw_latency_min_ms": raw_s[0] if raw_s else None,
            "raw_latency_p50_ms": percentile(raw_s, 50),
            "raw_latency_p95_ms": percentile(raw_s, 95),
            "raw_latency_p99_ms": percentile(raw_s, 99),
            "raw_latency_max_ms": raw_s[-1] if raw_s else None,
            "corrected_latency_min_ms": corr_s[0] if corr_s else None,
            "corrected_latency_p50_ms": percentile(corr_s, 50),
            "corrected_latency_p95_ms": percentile(corr_s, 95),
            "corrected_latency_p99_ms": percentile(corr_s, 99),
            "corrected_latency_max_ms": corr_s[-1] if corr_s else None,
            "negative_raw_latency_count": self.negative_raw_latency_count,
            "negative_corrected_latency_count": self.negative_corrected_latency_count,
        }


class BoundedDedup:
    def __init__(self, *, max_keys: int = 200_000, window_ms: int = 600_000) -> None:
        self.max_keys = max_keys
        self.window_ms = window_ms
        self._keys: dict[str, int] = {}
        self.duplicate_count = 0
        self.cross_partition_duplicate_count = 0

    def seen(self, key: str, now_ms: int) -> bool:
        # expire
        if len(self._keys) > self.max_keys * 0.9:
            cutoff = now_ms - self.window_ms
            self._keys = {k: t for k, t in self._keys.items() if t >= cutoff}
        if key in self._keys:
            self.duplicate_count += 1
            return True
        self._keys[key] = now_ms
        if len(self._keys) > self.max_keys:
            # drop oldest approx
            oldest = sorted(self._keys.items(), key=lambda x: x[1])[: len(self._keys) - self.max_keys]
            for k, _ in oldest:
                self._keys.pop(k, None)
        return False

    def report(self) -> dict[str, Any]:
        return {
            "dedup_window_size": self.max_keys,
            "dedup_window_duration": self.window_ms,
            "duplicate_count": self.duplicate_count,
            "cross_partition_duplicate_count": self.cross_partition_duplicate_count,
            "post_restart_duplicate_count": 0,
            "full_records_retained_in_memory": False,
        }
