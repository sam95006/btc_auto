"""Typed models for V18-C Eligible Universe."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    known: bool
    detail: str
    measured_value: float | str | bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InstrumentSnapshot:
    """Normalized public-catalog instrument + market metrics.

    Missing optional fields must remain None — never invent zeros for
    eligibility promotion.
    """

    symbol: str
    exchange: str = "bybit"
    category: str = "linear"
    status: str | None = None
    quote_coin: str | None = None
    base_coin: str | None = None
    launch_time_ms: int | None = None
    tick_size: float | None = None
    lot_size: float | None = None
    min_notional: float | None = None
    contract_type: str | None = None
    turnover_24h: float | None = None
    trade_count_24h: int | None = None
    spread_bps: float | None = None
    book_depth_usdt: float | None = None
    funding_rate: float | None = None
    funding_available: bool | None = None
    open_interest_value: float | None = None
    oi_available: bool | None = None
    history_bars: int | None = None
    data_completeness: float | None = None
    data_trust_status: str | None = None
    license_status: str | None = None
    delisting_flag: bool | None = None
    round_trip_cost_bps: float | None = None
    last_price: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class UniverseDecision:
    symbol: str
    universe_class: str
    gates: list[GateResult]
    reasons: list[str]
    funnel_stage_reached: str
    as_of_ms: int
    data_trust_status: str | None
    observe_only: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "universe_class": self.universe_class,
            "gates": [g.to_dict() for g in self.gates],
            "reasons": list(self.reasons),
            "funnel_stage_reached": self.funnel_stage_reached,
            "as_of_ms": self.as_of_ms,
            "data_trust_status": self.data_trust_status,
            "observe_only": self.observe_only,
        }
