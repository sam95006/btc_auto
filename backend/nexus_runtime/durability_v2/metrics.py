"""Latency histogram helpers for durability metrics."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def percentile(sorted_values: list[float], p: float) -> float | None:
    if not sorted_values:
        return None
    if p <= 0:
        return sorted_values[0]
    if p >= 100:
        return sorted_values[-1]
    k = (len(sorted_values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


@dataclass
class LatencyHistogram:
    """Collects latency samples (seconds) and reports p50/p95/p99."""

    name: str
    samples: list[float] = field(default_factory=list)

    def observe(self, seconds: float) -> None:
        if seconds < 0:
            return
        self.samples.append(float(seconds))

    def summary(self) -> dict[str, Any]:
        xs = sorted(self.samples)
        return {
            "name": self.name,
            "count": len(xs),
            "p50_s": percentile(xs, 50),
            "p95_s": percentile(xs, 95),
            "p99_s": percentile(xs, 99),
            "min_s": xs[0] if xs else None,
            "max_s": xs[-1] if xs else None,
            "mean_s": (sum(xs) / len(xs)) if xs else None,
        }
