"""Deterministic latency distributions for simulated microstructure.

Cancel-replace and decision-to-ack latencies are synthetic. They never
trigger exchange I/O.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LatencySample:
    decision_to_ack_ms: int
    ack_to_first_fill_ms: int
    cancel_replace_rtt_ms: int
    total_round_trip_ms: int

    def as_dict(self) -> dict[str, int]:
        return {
            "decision_to_ack_ms": self.decision_to_ack_ms,
            "ack_to_first_fill_ms": self.ack_to_first_fill_ms,
            "cancel_replace_rtt_ms": self.cancel_replace_rtt_ms,
            "total_round_trip_ms": self.total_round_trip_ms,
        }


# Discrete distribution buckets (ms) — founder-conservative synthetic.
_ACK_BUCKETS = (5, 12, 25, 40, 80, 150)
_FILL_BUCKETS = (0, 8, 20, 55, 120, 250)
_CXR_BUCKETS = (15, 30, 60, 100, 200, 400)


def _pick(buckets: tuple[int, ...], seed_material: str) -> int:
    digest = hashlib.sha256(seed_material.encode()).hexdigest()
    idx = int(digest[:8], 16) % len(buckets)
    return buckets[idx]


def sample_latency(*, scenario_id: int, seed: int, kind: str) -> LatencySample:
    ack = _pick(_ACK_BUCKETS, f"ack|{seed}|{scenario_id}|{kind}")
    fill = _pick(_FILL_BUCKETS, f"fill|{seed}|{scenario_id}|{kind}")
    cxr = _pick(_CXR_BUCKETS, f"cxr|{seed}|{scenario_id}|{kind}")
    return LatencySample(
        decision_to_ack_ms=ack,
        ack_to_first_fill_ms=fill,
        cancel_replace_rtt_ms=cxr,
        total_round_trip_ms=ack + fill,
    )


def latency_distribution_summary(samples: list[LatencySample]) -> dict[str, Any]:
    if not samples:
        return {"count": 0}
    acks = sorted(s.decision_to_ack_ms for s in samples)
    fills = sorted(s.ack_to_first_fill_ms for s in samples)
    cxrs = sorted(s.cancel_replace_rtt_ms for s in samples)

    def _pct(xs: list[int], p: float) -> int:
        if not xs:
            return 0
        idx = min(len(xs) - 1, max(0, int(round((p / 100.0) * (len(xs) - 1)))))
        return xs[idx]

    return {
        "count": len(samples),
        "decision_to_ack_ms": {"p50": _pct(acks, 50), "p95": _pct(acks, 95), "p99": _pct(acks, 99)},
        "ack_to_first_fill_ms": {"p50": _pct(fills, 50), "p95": _pct(fills, 95), "p99": _pct(fills, 99)},
        "cancel_replace_rtt_ms": {"p50": _pct(cxrs, 50), "p95": _pct(cxrs, 95), "p99": _pct(cxrs, 99)},
    }


__all__ = [
    "LatencySample",
    "latency_distribution_summary",
    "sample_latency",
]
