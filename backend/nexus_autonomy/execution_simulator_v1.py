"""NEXUS Autonomous Execution Simulator V1 — local deterministic simulated broker.

Never instantiates an authenticated exchange-write client.
HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE only.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


TAKER_FEE = 0.00055
MAKER_FEE = 0.00020
DEFAULT_SPREAD_BPS = 1.0
DEFAULT_SLIP_BPS = 2.0
MAX_LEVERAGE_CEILING = 50
DEFAULT_LEVERAGE = 25
MARGIN_MODE = "ISOLATED"

ORDER_STATES = (
    "CREATED",
    "ACCEPTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_PENDING",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
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


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:24]


@dataclass
class SimOrder:
    order_id: str
    intent_key: str
    symbol: str
    side: str
    order_type: str
    qty: float
    price: float | None
    stop_price: float | None = None
    reduce_only: bool = False
    state: str = "CREATED"
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    created_at: str = field(default_factory=_utc)
    reject_reason: str | None = None


@dataclass
class SimPosition:
    position_id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    leverage: int = DEFAULT_LEVERAGE
    margin_usdt: float = 20.0
    state: str = "OPEN"
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    funding_paid: float = 0.0


class AutonomousExecutionSimulatorV1:
    """Conservative deterministic fill model.

    A limit/stop does not fill merely because a candle *touched* the price.
    Fill requires price to trade *through* the level by at least 1 tick (adverse).
    Same-bar stop+target → BLOCKED_AMBIGUOUS (adverse-first policy).
    """

    def __init__(
        self,
        *,
        max_positions: int = 2,
        max_intents: int = 2,
        leverage: int = DEFAULT_LEVERAGE,
        margin_usdt: float = 20.0,
        tick_size: float = 0.1,
        lot_size: float = 0.001,
        min_notional: float = 5.0,
    ) -> None:
        if leverage > MAX_LEVERAGE_CEILING or leverage > 50:
            raise ValueError("leverage_exceeds_ceiling")
        if leverage == 100:
            raise ValueError("100x_forbidden")
        self.max_positions = max_positions
        self.max_intents = max_intents
        self.leverage = leverage
        self.margin_usdt = margin_usdt
        self.tick_size = tick_size
        self.lot_size = lot_size
        self.min_notional = min_notional
        self.orders: dict[str, SimOrder] = {}
        self.positions: dict[str, SimPosition] = {}
        self.intent_owners: dict[str, str] = {}
        self.exchange_write_attempt_count = 0
        self.demo_order_count = 0
        self.counts = {
            "order_created_count": 0,
            "partially_filled_count": 0,
            "filled_count": 0,
            "cancelled_count": 0,
            "rejected_count": 0,
            "unfilled_count": 0,
            "simulated_position_open_count": 0,
            "simulated_position_closed_count": 0,
            "simulated_liquidation_count": 0,
        }
        self.audit: list[dict[str, Any]] = []

    def _open_position_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.state in {"OPEN", "OPENING", "REDUCING"})

    def _pending_intent_count(self) -> int:
        return sum(1 for o in self.orders.values() if o.state in {"CREATED", "ACCEPTED", "PARTIALLY_FILLED", "CANCEL_PENDING"})

    def create_order(self, req: dict[str, Any]) -> dict[str, Any]:
        intent_key = req["idempotency_key"]
        if intent_key in self.intent_owners:
            return {
                "status": "DUPLICATE_IGNORED",
                "order_id": self.intent_owners[intent_key],
                "canonical_owner": self.intent_owners[intent_key],
            }
        if req.get("requested_actions"):
            forbidden = {"risk_increase", "stop_widening", "leverage_increase", "martingale", "averaging_down"}
            if set(req["requested_actions"]) & forbidden:
                return {"status": "REJECTED", "reason": "HARD_RISK_OVERRIDE_REJECTED", "order_or_policy_mutation": False}
        if req.get("margin_mode", MARGIN_MODE).upper() == "CROSS":
            return {"status": "REJECTED", "reason": "CROSS_MARGIN_FORBIDDEN"}
        if int(req.get("leverage") or self.leverage) > MAX_LEVERAGE_CEILING:
            return {"status": "REJECTED", "reason": "LEVERAGE_CEILING"}
        if self._open_position_count() >= self.max_positions and not req.get("reduce_only"):
            return {"status": "REJECTED", "reason": "MAX_POSITIONS"}
        if self._pending_intent_count() >= self.max_intents:
            return {"status": "REJECTED", "reason": "MAX_INTENTS"}

        qty = float(req["qty"])
        # lot size / min notional
        qty = math.floor(qty / self.lot_size) * self.lot_size
        px = float(req.get("price") or req.get("mark_price") or 0)
        if qty <= 0 or px * qty < self.min_notional:
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": "LOT_OR_NOTIONAL"}

        oid = _sha(f"{intent_key}|{req.get('symbol')}|{qty}")
        order = SimOrder(
            order_id=oid,
            intent_key=intent_key,
            symbol=req["symbol"],
            side=req["side"],
            order_type=req.get("order_type", "market"),
            qty=qty,
            price=req.get("price"),
            stop_price=req.get("stop_price"),
            reduce_only=bool(req.get("reduce_only")),
            state="ACCEPTED",
        )
        self.orders[oid] = order
        self.intent_owners[intent_key] = oid
        self.counts["order_created_count"] += 1
        return {"status": "ACCEPTED", "order_id": oid, "state": order.state}

    def _apply_costs(self, *, notional: float, is_taker: bool) -> dict[str, float]:
        fee_rate = TAKER_FEE if is_taker else MAKER_FEE
        entry_fee = notional * fee_rate
        spread = notional * (DEFAULT_SPREAD_BPS / 10000.0)
        slip = notional * (DEFAULT_SLIP_BPS / 10000.0)
        return {"entry_fee": entry_fee, "spread_cost": spread, "slippage_cost": slip, "fee_rate": fee_rate}

    def try_fill(
        self,
        order_id: str,
        *,
        market_bid: float,
        market_ask: float,
        last_price: float,
        path_low: float,
        path_high: float,
        same_bar_stop: float | None = None,
        same_bar_target: float | None = None,
        partial_ratio: float | None = None,
    ) -> dict[str, Any]:
        order = self.orders[order_id]
        if order.state in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}:
            return {"status": order.state, "order_id": order_id}

        # Adverse-first same-bar ambiguity
        if same_bar_stop is not None and same_bar_target is not None:
            hit_stop = path_low <= same_bar_stop <= path_high
            hit_target = path_low <= same_bar_target <= path_high
            if hit_stop and hit_target:
                order.state = "REJECTED"
                order.reject_reason = "SAME_BAR_STOP_TARGET_ADVERSE_FIRST"
                self.counts["rejected_count"] += 1
                return {"status": "BLOCKED_AMBIGUOUS", "reason": order.reject_reason}

        fill_px = None
        is_taker = True
        ot = order.order_type
        if ot == "market":
            fill_px = market_ask if order.side.upper() == "BUY" else market_bid
        elif ot == "limit":
            # Requires trade-through by 1 tick — touch alone is insufficient.
            assert order.price is not None
            if order.side.upper() == "BUY":
                if path_low <= (order.price - self.tick_size):
                    fill_px = order.price
                    is_taker = False
            else:
                if path_high >= (order.price + self.tick_size):
                    fill_px = order.price
                    is_taker = False
        elif ot in {"stop-market", "take-profit-market"}:
            assert order.stop_price is not None
            if order.side.upper() == "SELL" and path_low <= (order.stop_price - self.tick_size):
                fill_px = market_bid
            elif order.side.upper() == "BUY" and path_high >= (order.stop_price + self.tick_size):
                fill_px = market_ask
        else:
            order.state = "REJECTED"
            order.reject_reason = "UNSUPPORTED_ORDER_TYPE"
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": order.reject_reason}

        if fill_px is None:
            self.counts["unfilled_count"] += 1
            return {"status": "UNFILLED", "order_id": order_id, "state": order.state}

        fill_qty = order.qty
        if partial_ratio is not None and 0 < partial_ratio < 1:
            fill_qty = math.floor((order.qty * partial_ratio) / self.lot_size) * self.lot_size
            if fill_qty <= 0:
                return {"status": "UNFILLED", "order_id": order_id}
            order.filled_qty += fill_qty
            order.avg_fill_price = fill_px
            order.state = "PARTIALLY_FILLED"
            self.counts["partially_filled_count"] += 1
            if order.filled_qty + 1e-12 < order.qty:
                return {"status": "PARTIALLY_FILLED", "order_id": order_id, "filled_qty": order.filled_qty, "fill_price": fill_px}

        order.filled_qty = order.qty
        order.avg_fill_price = fill_px
        order.state = "FILLED"
        self.counts["filled_count"] += 1

        notional = fill_px * order.qty
        costs = self._apply_costs(notional=notional, is_taker=is_taker)
        if order.reduce_only:
            # close matching position
            closed = None
            for p in self.positions.values():
                if p.symbol == order.symbol and p.state == "OPEN":
                    exit_fee = notional * TAKER_FEE
                    gross = (fill_px - p.entry_price) * p.qty * (1 if p.side.upper() == "BUY" else -1)
                    # side semantics: long profit if exit > entry
                    if p.side.upper() == "LONG" or p.side.upper() == "BUY":
                        gross = (fill_px - p.entry_price) * p.qty
                    else:
                        gross = (p.entry_price - fill_px) * p.qty
                    net = gross - costs["entry_fee"] - exit_fee - costs["spread_cost"] - costs["slippage_cost"] - p.funding_paid
                    p.state = "CLOSED"
                    p.realized_pnl = net
                    self.counts["simulated_position_closed_count"] += 1
                    closed = {
                        "position_id": p.position_id,
                        "gross_pnl": gross,
                        "exit_fee": exit_fee,
                        "entry_fee": costs["entry_fee"],
                        "spread_cost": costs["spread_cost"],
                        "slippage_cost": costs["slippage_cost"],
                        "funding_cost": p.funding_paid,
                        "net_pnl": net,
                    }
                    break
            return {"status": "FILLED", "order_id": order_id, "fill_price": fill_px, "close": closed, "costs": costs}

        pid = _sha(f"pos|{order.intent_key}")
        side = "LONG" if order.side.upper() == "BUY" else "SHORT"
        pos = SimPosition(
            position_id=pid,
            symbol=order.symbol,
            side=side,
            qty=order.qty,
            entry_price=fill_px,
            leverage=self.leverage,
            margin_usdt=self.margin_usdt,
            state="OPEN",
        )
        self.positions[pid] = pos
        self.counts["simulated_position_open_count"] += 1
        # liquidation distance check (isolated): rough maint
        liq_distance = self.margin_usdt * self.leverage * 0.5 / max(order.qty, 1e-9)
        return {
            "status": "FILLED",
            "order_id": order_id,
            "position_id": pid,
            "fill_price": fill_px,
            "costs": costs,
            "liquidation_distance": liq_distance,
        }

    def cancel(self, order_id: str) -> dict[str, Any]:
        order = self.orders[order_id]
        if order.state in {"FILLED", "CANCELLED", "REJECTED"}:
            return {"status": order.state}
        order.state = "CANCELLED"
        self.counts["cancelled_count"] += 1
        return {"status": "CANCELLED", "order_id": order_id}

    def apply_funding(self, position_id: str, rate: float) -> None:
        p = self.positions[position_id]
        notional = p.entry_price * p.qty
        p.funding_paid += abs(notional * rate)

    def open_ambiguous_position_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.state == "BLOCKED_AMBIGUOUS")

    def unclosed_intent_count(self) -> int:
        return self._pending_intent_count()

    def report(self) -> dict[str, Any]:
        return {
            **self.counts,
            "open_ambiguous_position_count": self.open_ambiguous_position_count(),
            "unclosed_intent_count": self.unclosed_intent_count(),
            "exchange_write_attempt_count": self.exchange_write_attempt_count,
            "demo_order_count": self.demo_order_count,
            "max_positions": self.max_positions,
            "max_intents": self.max_intents,
            "leverage": self.leverage,
            "margin_mode": MARGIN_MODE,
            "fill_policy": "TRADE_THROUGH_ONE_TICK_REQUIRED; TOUCH_ALONE_INSUFFICIENT; SAME_BAR_STOP_TARGET=BLOCKED_AMBIGUOUS",
            "fee_policy": {"taker": TAKER_FEE, "maker": MAKER_FEE},
        }
