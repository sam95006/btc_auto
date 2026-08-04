"""Execution fill/order/position models for Autonomous Execution Simulator V1.1.

Local simulation only — no exchange-write transport.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ORDER_STATES = (
    "CREATED",
    "ACCEPTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_PENDING",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
    "REPLACED",
)

POSITION_STATES = (
    "NONE",
    "OPENING",
    "OPEN",
    "REDUCING",
    "CLOSED",
    "LIQUIDATED_SIMULATED",
    "BLOCKED_AMBIGUOUS",
)

INSTRUMENT_STATUSES = ("TRADING", "HALT", "SETTLE", "DELISTED")

TIME_IN_FORCE = ("GTC", "IOC", "FOK", "GTD")

FILL_POLICY_DOC = (
    "TRADE_THROUGH_ONE_TICK_REQUIRED; "
    "TOUCH_ALONE_INSUFFICIENT; "
    "QUEUE_AWARE_CONSERVATIVE_LIMIT; "
    "CANDLE_TOUCH_NEVER_EQUALS_FILL; "
    "SAME_BAR_STOP_TARGET=BLOCKED_AMBIGUOUS_ADVERSE_FIRST; "
    "MARK_PRICE_TRIGGER_FOR_STOPS; "
    "INDEX_PRICE_REQUIRED_FOR_MARK_DERIVATION"
)


@dataclass
class InstrumentSpec:
    symbol: str
    tick_size: float = 0.1
    qty_step: float = 0.001
    min_notional: float = 5.0
    status: str = "TRADING"
    maint_margin_rate: float = 0.005
    max_leverage: int = 50


@dataclass
class SimOrderV11:
    order_id: str
    intent_key: str
    symbol: str
    side: str
    order_type: str
    qty: float
    price: float | None
    stop_price: float | None = None
    reduce_only: bool = False
    time_in_force: str = "GTC"
    expires_at_ms: int | None = None
    state: str = "CREATED"
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    created_at_ms: int = 0
    reject_reason: str | None = None
    replace_of: str | None = None
    latency_ms: int = 0
    queue_ahead_qty: float = 0.0
    fills: list[dict[str, Any]] = field(default_factory=list)

    @property
    def remaining_qty(self) -> float:
        return max(0.0, self.qty - self.filled_qty)


@dataclass
class SimPositionV11:
    position_id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    leverage: int
    margin_usdt: float
    state: str = "OPEN"
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    funding_paid: float = 0.0
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    liquidation_price: float | None = None
    residual_qty: float = 0.0

    @property
    def gross_exposure(self) -> float:
        return abs(self.qty)


@dataclass
class FillEventV11:
    order_id: str
    fill_qty: float
    fill_price: float
    is_taker: bool
    fee: float
    spread_cost: float
    slippage_cost: float
    ts_ms: int
    reason: str
