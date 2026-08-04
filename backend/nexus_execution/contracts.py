"""V1.1 execution contracts.

Immutable, versioned data classes shared between the execution simulator and
its callers (e.g. Agent B's session orchestrator via a compatibility shim).

Design rules:

* Every dataclass here is ``frozen=True`` so the simulator cannot mutate a
  contract instance in place.
* Every monetary or price field is a :class:`decimal.Decimal` so cost-bridge
  equality holds to the cent, not to a floating point epsilon.
* Every enum-like set is a ``frozenset[str]`` — using bare strings keeps
  JSON serialization trivial for readiness artifacts while allowing strict
  membership checks.
* Any breaking change requires a *new* file (``contracts_v1_2.py``); this
  file must not gain or remove attributes without a version bump.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

CONTRACT_VERSION = "execution_contract_v1_1"

# --- Enumerations ----------------------------------------------------------

ORDER_TYPES: frozenset[str] = frozenset({
    "MARKET",
    "LIMIT",
    "STOP_MARKET",
    "TAKE_PROFIT_MARKET",
})

ORDER_STATES: frozenset[str] = frozenset({
    "CREATED",
    "ACCEPTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_PENDING",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
})

POSITION_STATES: frozenset[str] = frozenset({
    "NONE",
    "OPENING",
    "OPEN",
    "REDUCING",
    "CLOSED",
    "LIQUIDATED_SIMULATED",
    "BLOCKED_AMBIGUOUS",
})

SIDES: frozenset[str] = frozenset({"BUY", "SELL"})

MARGIN_MODES: frozenset[str] = frozenset({"ISOLATED"})  # CROSS is banned system-wide.


# Legal state transitions for orders. Anything not listed here is invalid.
ORDER_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    ("CREATED", "ACCEPTED"),
    ("CREATED", "REJECTED"),
    ("ACCEPTED", "PARTIALLY_FILLED"),
    ("ACCEPTED", "FILLED"),
    ("ACCEPTED", "CANCEL_PENDING"),
    ("ACCEPTED", "CANCELLED"),
    ("ACCEPTED", "EXPIRED"),
    ("ACCEPTED", "REJECTED"),
    ("PARTIALLY_FILLED", "PARTIALLY_FILLED"),
    ("PARTIALLY_FILLED", "FILLED"),
    ("PARTIALLY_FILLED", "CANCEL_PENDING"),
    ("PARTIALLY_FILLED", "CANCELLED"),
    ("PARTIALLY_FILLED", "EXPIRED"),
    ("CANCEL_PENDING", "CANCELLED"),
    ("CANCEL_PENDING", "FILLED"),  # race: fill wins before cancel confirms
})

# Legal state transitions for positions.
POSITION_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    ("NONE", "OPENING"),
    ("OPENING", "OPEN"),
    ("OPENING", "BLOCKED_AMBIGUOUS"),
    ("OPEN", "REDUCING"),
    ("OPEN", "CLOSED"),
    ("OPEN", "LIQUIDATED_SIMULATED"),
    ("REDUCING", "OPEN"),
    ("REDUCING", "CLOSED"),
    ("REDUCING", "LIQUIDATED_SIMULATED"),
    ("BLOCKED_AMBIGUOUS", "CLOSED"),
})


# --- Instrument -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Static per-symbol trading rules."""

    symbol: str
    tick_size: Decimal
    lot_size: Decimal
    min_notional: Decimal
    status: str = "TRADING"  # TRADING | HALTED | AUCTION_ONLY
    maker_fee: Decimal = Decimal("0.0002")
    taker_fee: Decimal = Decimal("0.00055")

    def is_tradable(self) -> bool:
        return self.status == "TRADING"


# --- Orders ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """Immutable request handed to the simulator.

    The simulator hashes ``idempotency_key`` to a canonical ``order_id`` and
    guarantees at most one ``OrderRecord`` per intent for the lifetime of the
    process.
    """

    idempotency_key: str
    symbol: str
    side: str  # BUY | SELL
    order_type: str  # MARKET | LIMIT | STOP_MARKET | TAKE_PROFIT_MARKET
    qty: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None
    reduce_only: bool = False
    leverage: int = 25
    margin_mode: str = "ISOLATED"
    time_in_force: str = "GTC"  # GTC | IOC | FOK
    expires_at_bar: int | None = None
    requested_actions: tuple[str, ...] = ()
    client_tag: str | None = None


@dataclass(frozen=True, slots=True)
class FillEvent:
    """A single fill against an order (there may be many for a partial fill)."""

    order_id: str
    fill_id: str
    qty: Decimal
    price: Decimal
    fee: Decimal
    is_taker: bool
    bar_index: int


@dataclass
class OrderRecord:
    """Mutable state kept by the simulator for a live/terminal order.

    Held as a regular dataclass — not frozen — because state transitions and
    partial-fill accounting need to mutate the record. All transitions must
    pass through ``advance_state`` so illegal transitions are rejected.
    """

    order_id: str
    intent: OrderIntent
    state: str
    filled_qty: Decimal = Decimal(0)
    avg_fill_price: Decimal = Decimal(0)
    fills: list[FillEvent] = field(default_factory=list)
    reject_reason: str | None = None
    cancel_reason: str | None = None
    accumulated_fee: Decimal = Decimal(0)
    cancel_replace_count: int = 0
    partial_fill_count: int = 0
    created_bar: int = 0
    last_bar: int = 0

    def advance_state(self, new_state: str) -> None:
        transition = (self.state, new_state)
        if transition not in ORDER_TRANSITIONS and new_state != self.state:
            raise ValueError(
                f"illegal_order_transition {self.state}->{new_state} order_id={self.order_id}"
            )
        self.state = new_state


@dataclass
class PositionRecord:
    """Mutable state for a simulated position."""

    position_id: str
    symbol: str
    side: str  # LONG | SHORT
    qty: Decimal
    avg_entry_price: Decimal
    leverage: int
    margin_usdt: Decimal
    state: str = "OPENING"
    unrealized_pnl: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    funding_debit: Decimal = Decimal(0)
    funding_credit: Decimal = Decimal(0)
    liquidation_price: Decimal | None = None

    def advance_state(self, new_state: str) -> None:
        transition = (self.state, new_state)
        if transition not in POSITION_TRANSITIONS and new_state != self.state:
            raise ValueError(
                f"illegal_position_transition {self.state}->{new_state} pos={self.position_id}"
            )
        self.state = new_state


# --- Cost bridge ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostBridge:
    """Cost decomposition for a *completed* simulated trade.

    Invariant (checked in ``verify``):
      gross_pnl
        - entry_fee - exit_fee
        - spread_cost - slippage_cost
        - funding_cost
        - partial_fill_cost
        - cancel_replace_cost
        == net_pnl
    """

    gross_pnl: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    funding_cost: Decimal  # signed: positive = debit, negative = credit
    partial_fill_cost: Decimal
    cancel_replace_cost: Decimal
    net_pnl: Decimal

    def verify(self) -> bool:
        derived = (
            self.gross_pnl
            - self.entry_fee
            - self.exit_fee
            - self.spread_cost
            - self.slippage_cost
            - self.funding_cost
            - self.partial_fill_cost
            - self.cancel_replace_cost
        )
        return derived == self.net_pnl

    def as_dict(self) -> dict[str, str]:
        return {
            "gross_pnl": format(self.gross_pnl, "f"),
            "entry_fee": format(self.entry_fee, "f"),
            "exit_fee": format(self.exit_fee, "f"),
            "spread_cost": format(self.spread_cost, "f"),
            "slippage_cost": format(self.slippage_cost, "f"),
            "funding_cost": format(self.funding_cost, "f"),
            "partial_fill_cost": format(self.partial_fill_cost, "f"),
            "cancel_replace_cost": format(self.cancel_replace_cost, "f"),
            "net_pnl": format(self.net_pnl, "f"),
        }


@dataclass(frozen=True, slots=True)
class CompletedTrade:
    """A closed round-trip position with its full cost bridge."""

    position_id: str
    symbol: str
    side: str
    qty: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_order_id: str
    exit_order_id: str
    cost_bridge: CostBridge
    open_bar: int
    close_bar: int
    liquidated: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": format(self.qty, "f"),
            "entry_price": format(self.entry_price, "f"),
            "exit_price": format(self.exit_price, "f"),
            "entry_order_id": self.entry_order_id,
            "exit_order_id": self.exit_order_id,
            "cost_bridge": self.cost_bridge.as_dict(),
            "open_bar": self.open_bar,
            "close_bar": self.close_bar,
            "liquidated": self.liquidated,
        }
