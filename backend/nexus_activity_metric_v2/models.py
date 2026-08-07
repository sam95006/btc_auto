"""Core models for Official Activity Metric V2."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from backend.nexus_activity_metric_v2.constants import (
    ACTIVITY_QUALITY_STATES,
    DEFAULT_WINDOW_MS,
    SCHEMA,
    SCHEMA_VERSION,
)

ActivityQualityState = Literal[
    "LIVE",
    "INSUFFICIENT_HISTORY",
    "STALE",
    "UNAVAILABLE",
    "DEGRADED",
]


@dataclass(frozen=True)
class TradeEvent:
    """Normalized public trade event (REST or WS)."""

    trade_id: str
    symbol: str
    price: float
    size: float
    side: str  # Buy | Sell
    event_time_ms: int
    receive_time_ms: int
    source: str
    notional: float | None = None

    def __post_init__(self) -> None:
        if not self.trade_id:
            raise ValueError("trade_id_required")
        if not self.symbol:
            raise ValueError("symbol_required")
        if self.price < 0 or self.size < 0:
            raise ValueError("price_size_must_be_non_negative")

    @property
    def computed_notional(self) -> float:
        if self.notional is not None:
            return float(self.notional)
        return float(self.price) * float(self.size)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TradeEvent":
        return cls(
            trade_id=str(raw["trade_id"]),
            symbol=str(raw["symbol"]),
            price=float(raw["price"]),
            size=float(raw["size"]),
            side=str(raw.get("side") or ""),
            event_time_ms=int(raw["event_time_ms"]),
            receive_time_ms=int(raw["receive_time_ms"]),
            source=str(raw.get("source") or "unknown"),
            notional=(
                float(raw["notional"]) if raw.get("notional") is not None else None
            ),
        )


@dataclass
class BuySellActivity:
    buy_count: int = 0
    sell_count: int = 0
    buy_notional: float = 0.0
    sell_notional: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActivityMetrics:
    """Official window metrics — distinct from Gate field trade_count_24h."""

    symbol: str
    trade_count_window: int
    trade_notional_window: float
    unique_trade_count: int
    buy_sell_activity: BuySellActivity
    event_time_ms: int | None
    receive_time_ms: int | None
    freshness_ms: int | None
    coverage_start_ms: int | None
    coverage_end_ms: int | None
    warmup_complete: bool
    quality_state: str
    source: str
    window_ms: int = DEFAULT_WINDOW_MS
    schema: str = SCHEMA
    schema_version: int = SCHEMA_VERSION
    # Explicit versioned proxy note — never overwrite trade_count_24h silently.
    gate_field_proxy: dict[str, Any] = field(
        default_factory=lambda: {
            "maps_to_gate_field": "trade_count_24h",
            "proxy_metric": "trade_count_window",
            "proxy_version": "activity_metric_v2",
            "silent_substitution_forbidden": True,
            "volume24h_is_not_trade_count": True,
            "turnover24h_is_not_trade_count": True,
        }
    )

    def __post_init__(self) -> None:
        if self.quality_state not in ACTIVITY_QUALITY_STATES:
            raise ValueError(f"invalid_quality_state={self.quality_state}")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d
