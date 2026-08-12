"""Shared Structural Geometry contracts — leaf module (no sim/qualify imports).

Breaks the geometry_event_sim ↔ structural_geometry_qualify import cycle by
hosting CandidateEvidence as a shared contract both sides depend on.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CandidateEvidence:
    """Evidence-backed geometry inputs. Missing fields must not be invented."""

    symbol: str
    side: str
    entry_price: float
    regime: str = "UNKNOWN"
    strategy: str = "UNKNOWN"
    atr: float | None = None
    recent_swing_high: float | None = None
    recent_swing_low: float | None = None
    support: float | None = None
    resistance: float | None = None
    liquidity_levels: list[float] = field(default_factory=list)
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    fee_rate: float | None = None
    funding_rate: float | None = None
    tick_size: float | None = None
    qty: float | None = None
    data_freshness_sec: float | None = None
    max_freshness_sec: float = 300.0
    ts: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
