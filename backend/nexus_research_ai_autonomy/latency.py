"""Latency telemetry §18–19 for fast-path Research Demo orders."""
from __future__ import annotations

import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class LatencyTrace:
    decision_id: str = ""
    market_event_ts: int = 0
    feature_ready_ts: int = 0
    trigger_ts: int = 0
    risk_start_ts: int = 0
    risk_pass_ts: int = 0
    order_intent_ts: int = 0
    http_send_ts: int = 0
    exchange_ack_ts: int = 0
    fill_ts: int = 0
    slow_path_leak: bool = False

    def mark(self, field_name: str, ts: int | None = None) -> None:
        setattr(self, field_name, ts if ts is not None else _now_ms())

    def deltas_ms(self) -> dict[str, int | None]:
        def d(a: int, b: int) -> int | None:
            if a and b and b >= a:
                return b - a
            return None

        return {
            "market_to_trigger_ms": d(self.market_event_ts, self.trigger_ts),
            "trigger_to_risk_ms": d(self.trigger_ts, self.risk_start_ts),
            "risk_to_send_ms": d(self.risk_pass_ts, self.http_send_ts),
            "trigger_to_send_ms": d(self.trigger_ts, self.http_send_ts),
            "send_to_ack_ms": d(self.http_send_ts, self.exchange_ack_ts),
            "ack_to_fill_ms": d(self.exchange_ack_ts, self.fill_ts),
            "market_to_fill_ms": d(self.market_event_ts, self.fill_ts),
        }

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["deltas_ms"] = self.deltas_ms()
        return out


@dataclass
class LatencyAggregator:
    traces: list[LatencyTrace] = field(default_factory=list)

    def add(self, trace: LatencyTrace) -> None:
        self.traces.append(trace)

    def _percentile(self, values: list[float], p: float) -> float | None:
        if not values:
            return None
        if len(values) == 1:
            return float(values[0])
        values = sorted(values)
        k = (len(values) - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, len(values) - 1)
        if f == c:
            return float(values[f])
        return float(values[f] + (values[c] - values[f]) * (k - f))

    def summary(self) -> dict[str, Any]:
        keys = [
            "trigger_to_send_ms",
            "send_to_ack_ms",
            "ack_to_fill_ms",
            "market_to_fill_ms",
        ]
        out: dict[str, Any] = {
            "n_traces": len(self.traces),
            "slow_path_leak_count": sum(1 for t in self.traces if t.slow_path_leak),
        }
        for key in keys:
            vals = []
            for t in self.traces:
                d = t.deltas_ms().get(key)
                if d is not None:
                    vals.append(float(d))
            prefix = key.replace("_ms", "")
            out[f"{prefix}_p50_ms"] = self._percentile(vals, 50)
            out[f"{prefix}_p95_ms"] = self._percentile(vals, 95)
            out[f"{prefix}_max_ms"] = max(vals) if vals else None
            if vals:
                out[f"{prefix}_mean_ms"] = float(statistics.fmean(vals))
        return out
