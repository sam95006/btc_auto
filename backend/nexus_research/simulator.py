"""Phase 5 Gate C — Simulated Order Execution Engine.

RESEARCH ONLY. No real exchange API. No real orders. No wallet access.
researchOnly=true on all outputs.

Supports:
  - MARKET and LIMIT order types
  - Order states: PENDING / PARTIAL / FILLED / CANCELLED / EXPIRED / REJECTED
  - Bid/ask spread slippage, taker/maker fees, funding rate accrual
  - Configurable fill latency, price precision, margin/leverage
  - Unrealised and realised PnL computation
  - Config-driven slippage and fee models
  - Thread-safe in-memory state; no persistence to production systems
"""
from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from collections import deque
from typing import Any

from backend.nexus_research.domain_events import (
    SIM_PLACEHOLDER_CREATED,
    SIM_PLACEHOLDER_UPDATED,
    publish_event,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
RESEARCH_ONLY: bool = True

# Order types
ORDER_MARKET = "MARKET"
ORDER_LIMIT = "LIMIT"

# Order sides
SIDE_LONG = "LONG"
SIDE_SHORT = "SHORT"

# Order states
STATE_PENDING = "PENDING"
STATE_PARTIAL = "PARTIAL"
STATE_FILLED = "FILLED"
STATE_CANCELLED = "CANCELLED"
STATE_EXPIRED = "EXPIRED"
STATE_REJECTED = "REJECTED"

# Position states
POS_OPEN = "OPEN"
POS_CLOSED = "CLOSED"

# Default config
_DEFAULT_CONFIG: dict[str, Any] = {
    "spread_bps": 2,           # bid/ask half-spread in basis points
    "slippage_market_bps": 3,  # additional slippage for MARKET orders (bps)
    "taker_fee_bps": 5,        # taker fee (bps of notional)
    "maker_fee_bps": 2,        # maker fee (bps)
    "funding_rate_8h": 0.01,   # funding rate per 8h window (percent)
    "fill_latency_ms": 50,     # simulated fill latency in ms
    "price_precision": 2,      # decimal places for price
    "qty_precision": 4,        # decimal places for qty
    "max_leverage": 20.0,
    "default_leverage": 5.0,
    "max_orders_history": 500,
    "limit_order_expire_ms": 3_600_000,  # 1 hour
}

_MAX_POSITIONS_HISTORY = 200


class SimOrder:
    """Simulated order record."""

    def __init__(
        self,
        order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        limit_price: float | None,
        leverage: float,
        config: dict[str, Any],
        correlation_id: str | None = None,
    ) -> None:
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.qty = qty
        self.limit_price = limit_price
        self.leverage = leverage
        self.config = config
        self.correlation_id = correlation_id

        self.state = STATE_PENDING
        self.filled_qty: float = 0.0
        self.avg_fill_price: float = 0.0
        self.fee_paid: float = 0.0
        self.reject_reason: str | None = None
        self.created_at_ms: int = int(time.time() * 1000)
        self.updated_at_ms: int = self.created_at_ms
        self.filled_at_ms: int | None = None
        self.expire_at_ms: int = self.created_at_ms + config.get(
            "limit_order_expire_ms", _DEFAULT_CONFIG["limit_order_expire_ms"]
        )
        self.fill_events: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "orderId": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "orderType": self.order_type,
            "qty": self.qty,
            "limitPrice": self.limit_price,
            "leverage": self.leverage,
            "state": self.state,
            "filledQty": self.filled_qty,
            "avgFillPrice": self.avg_fill_price,
            "feePaid": self.fee_paid,
            "rejectReason": self.reject_reason,
            "createdAtMs": self.created_at_ms,
            "updatedAtMs": self.updated_at_ms,
            "filledAtMs": self.filled_at_ms,
            "expireAtMs": self.expire_at_ms,
            "fillEvents": self.fill_events,
            "researchOnly": True,
        }


class SimPosition:
    """Simulated open/closed position."""

    def __init__(
        self,
        position_id: str,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        leverage: float,
        entry_fee: float,
        opened_at_ms: int,
        source_order_id: str,
    ) -> None:
        self.position_id = position_id
        self.symbol = symbol
        self.side = side
        self.qty = qty
        self.entry_price = entry_price
        self.leverage = leverage
        self.entry_fee = entry_fee
        self.opened_at_ms = opened_at_ms
        self.source_order_id = source_order_id

        self.state = POS_OPEN
        self.exit_price: float | None = None
        self.exit_fee: float = 0.0
        self.closed_at_ms: int | None = None
        self.funding_accrued: float = 0.0
        self.unrealised_pnl: float = 0.0
        self.realised_pnl: float | None = None
        self.last_mark_price: float = entry_price
        self.updated_at_ms: int = opened_at_ms

    @property
    def notional(self) -> float:
        return self.qty * self.entry_price

    def mark(self, mark_price: float, funding_bps: float = 0.0) -> None:
        """Update unrealised PnL with a new mark price and apply funding."""
        self.last_mark_price = mark_price
        price_delta = (mark_price - self.entry_price) if self.side == SIDE_LONG else (
            self.entry_price - mark_price
        )
        self.unrealised_pnl = price_delta * self.qty - self.entry_fee - self.funding_accrued
        if funding_bps:
            funding_payment = self.notional * funding_bps / 10_000.0
            if self.side == SIDE_LONG:
                self.funding_accrued += funding_payment
            else:
                self.funding_accrued -= funding_payment
            self.unrealised_pnl -= funding_payment
        self.updated_at_ms = int(time.time() * 1000)

    def close(self, exit_price: float, exit_fee: float) -> float:
        """Close position, compute realised PnL."""
        self.state = POS_CLOSED
        self.exit_price = exit_price
        self.exit_fee = exit_fee
        self.closed_at_ms = int(time.time() * 1000)
        self.updated_at_ms = self.closed_at_ms
        price_delta = (exit_price - self.entry_price) if self.side == SIDE_LONG else (
            self.entry_price - exit_price
        )
        self.realised_pnl = price_delta * self.qty - self.entry_fee - exit_fee - self.funding_accrued
        self.unrealised_pnl = 0.0
        return self.realised_pnl

    def to_dict(self) -> dict[str, Any]:
        return {
            "positionId": self.position_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "entryPrice": self.entry_price,
            "leverage": self.leverage,
            "entryFee": self.entry_fee,
            "openedAtMs": self.opened_at_ms,
            "sourceOrderId": self.source_order_id,
            "state": self.state,
            "exitPrice": self.exit_price,
            "exitFee": self.exit_fee,
            "closedAtMs": self.closed_at_ms,
            "fundingAccrued": self.funding_accrued,
            "unrealisedPnl": self.unrealised_pnl,
            "realisedPnl": self.realised_pnl,
            "lastMarkPrice": self.last_mark_price,
            "notional": self.notional,
            "updatedAtMs": self.updated_at_ms,
            "researchOnly": True,
        }


class SimulatedExchange:
    """Thread-safe simulated exchange. Research-only. No real API.

    Usage:
        exchange = SimulatedExchange(config={"spread_bps": 3})
        order_id = exchange.submit_order("BTCUSDT", SIDE_LONG, ORDER_MARKET, qty=0.001)
        exchange.process_pending_orders({"BTCUSDT": 65000.0})
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = {**_DEFAULT_CONFIG, **(config or {})}
        self._lock = threading.RLock()
        self._orders: dict[str, SimOrder] = {}
        self._order_history: deque[SimOrder] = deque(
            maxlen=self._config["max_orders_history"]
        )
        self._positions: dict[str, SimPosition] = {}  # position_id -> position
        self._open_positions_by_symbol: dict[str, list[str]] = {}  # symbol -> [pos_id]
        self._closed_positions: deque[SimPosition] = deque(maxlen=_MAX_POSITIONS_HISTORY)
        self._kill_switch: bool = False
        self._total_orders = 0
        self._total_fills = 0
        self._total_rejects = 0
        self._started_at_ms = int(time.time() * 1000)

    # ── Order submission ───────────────────────────────────────────────────────

    def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        limit_price: float | None = None,
        leverage: float | None = None,
        correlation_id: str | None = None,
    ) -> str:
        """Submit a simulated order. Returns order_id."""
        if self._kill_switch:
            order_id = str(uuid.uuid4())
            logger.warning("[sim] kill switch active — rejecting order %s", order_id)
            return self._reject_order(
                symbol, side, order_type, qty, limit_price,
                leverage or self._config["default_leverage"],
                "KILL_SWITCH_ACTIVE", order_id, correlation_id
            )

        _lev = min(
            float(leverage or self._config["default_leverage"]),
            float(self._config["max_leverage"]),
        )
        qty = round(qty, self._config["qty_precision"])

        if qty <= 0:
            return self._reject_order(
                symbol, side, order_type, qty, limit_price, _lev,
                "INVALID_QTY", str(uuid.uuid4()), correlation_id
            )

        order_id = str(uuid.uuid4())
        order = SimOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            limit_price=limit_price,
            leverage=_lev,
            config=self._config,
            correlation_id=correlation_id,
        )

        with self._lock:
            self._orders[order_id] = order
            self._total_orders += 1

        publish_event(
            SIM_PLACEHOLDER_CREATED,
            {"orderId": order_id, "symbol": symbol, "side": side,
             "qty": qty, "orderType": order_type, "researchOnly": True},
            idempotency_key=f"sim_order_{order_id}",
        )
        logger.debug("[sim] order submitted %s %s %s qty=%s", order_id, symbol, side, qty)
        return order_id

    def _reject_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        limit_price: float | None,
        leverage: float,
        reason: str,
        order_id: str,
        correlation_id: str | None,
    ) -> str:
        order = SimOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            limit_price=limit_price,
            leverage=leverage,
            config=self._config,
            correlation_id=correlation_id,
        )
        order.state = STATE_REJECTED
        order.reject_reason = reason
        with self._lock:
            self._order_history.append(order)
            self._total_rejects += 1
        return order_id

    # ── Order processing ───────────────────────────────────────────────────────

    def process_pending_orders(
        self,
        mark_prices: dict[str, float],
        funding_rates: dict[str, float] | None = None,
    ) -> list[str]:
        """Fill/expire pending orders against current mark prices. Returns filled order_ids."""
        if self._kill_switch:
            return []
        now_ms = int(time.time() * 1000)
        filled: list[str] = []

        with self._lock:
            pending = [o for o in self._orders.values() if o.state in (STATE_PENDING, STATE_PARTIAL)]

        for order in pending:
            mark = mark_prices.get(order.symbol)
            if mark is None:
                continue

            now_ms = int(time.time() * 1000)
            # Check expiry for LIMIT orders
            if order.order_type == ORDER_LIMIT and now_ms > order.expire_at_ms:
                with self._lock:
                    order.state = STATE_EXPIRED
                    order.updated_at_ms = now_ms
                    self._order_history.append(order)
                    self._orders.pop(order.order_id, None)
                continue

            # Determine fill price
            fill_price = self._compute_fill_price(order, mark)

            # LIMIT orders: check if limit is crossed
            if order.order_type == ORDER_LIMIT and order.limit_price is not None:
                if order.side == SIDE_LONG and fill_price > order.limit_price:
                    continue
                if order.side == SIDE_SHORT and fill_price < order.limit_price:
                    continue

            # Apply fill latency (simulate)
            if now_ms < order.created_at_ms + self._config["fill_latency_ms"]:
                continue

            fee_bps = (
                self._config["taker_fee_bps"]
                if order.order_type == ORDER_MARKET
                else self._config["maker_fee_bps"]
            )
            fee = order.qty * fill_price * fee_bps / 10_000.0
            fill_notional = order.qty * fill_price

            fill_event = {
                "fillId": str(uuid.uuid4()),
                "price": fill_price,
                "qty": order.qty,
                "notional": fill_notional,
                "fee": fee,
                "filledAtMs": now_ms,
            }

            with self._lock:
                order.filled_qty = order.qty
                order.avg_fill_price = fill_price
                order.fee_paid = fee
                order.state = STATE_FILLED
                order.filled_at_ms = now_ms
                order.updated_at_ms = now_ms
                order.fill_events.append(fill_event)
                self._total_fills += 1
                self._order_history.append(order)
                self._orders.pop(order.order_id, None)
                filled.append(order.order_id)

                # Open a position
                pos = self._open_position(order, fill_price, fee)
                # Apply funding if provided
                if funding_rates and order.symbol in funding_rates:
                    pos.mark(fill_price, funding_rates[order.symbol])

            publish_event(
                SIM_PLACEHOLDER_UPDATED,
                {"orderId": order.order_id, "state": STATE_FILLED,
                 "fillPrice": fill_price, "fee": fee, "researchOnly": True},
                idempotency_key=f"sim_fill_{order.order_id}",
            )

        # Mark open positions with latest prices + funding
        with self._lock:
            for pos in self._positions.values():
                if pos.state == POS_OPEN and pos.symbol in mark_prices:
                    funding_bps = (funding_rates or {}).get(pos.symbol, 0.0)
                    pos.mark(mark_prices[pos.symbol], funding_bps)

        return filled

    def _compute_fill_price(self, order: SimOrder, mark_price: float) -> float:
        """Apply spread + slippage to compute a fill price."""
        spread_half = mark_price * self._config["spread_bps"] / 10_000.0
        slippage = 0.0
        if order.order_type == ORDER_MARKET:
            slippage = mark_price * self._config["slippage_market_bps"] / 10_000.0

        if order.side == SIDE_LONG:
            fill = mark_price + spread_half + slippage
        else:
            fill = mark_price - spread_half - slippage

        precision = self._config["price_precision"]
        return round(fill, precision)

    def _open_position(self, order: SimOrder, fill_price: float, fee: float) -> SimPosition:
        pos_id = str(uuid.uuid4())
        pos = SimPosition(
            position_id=pos_id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            entry_price=fill_price,
            leverage=order.leverage,
            entry_fee=fee,
            opened_at_ms=int(time.time() * 1000),
            source_order_id=order.order_id,
        )
        self._positions[pos_id] = pos
        self._open_positions_by_symbol.setdefault(order.symbol, []).append(pos_id)
        return pos

    # ── Position management ────────────────────────────────────────────────────

    def close_position(
        self,
        position_id: str,
        mark_prices: dict[str, float],
    ) -> float | None:
        """Close a position at current mark. Returns realised PnL or None."""
        with self._lock:
            pos = self._positions.get(position_id)
            if pos is None or pos.state != POS_OPEN:
                return None
            mark = mark_prices.get(pos.symbol)
            if mark is None:
                return None

            fill_price = self._compute_fill_price_for_close(pos, mark)
            fee_bps = self._config["taker_fee_bps"]
            exit_fee = pos.qty * fill_price * fee_bps / 10_000.0
            pnl = pos.close(fill_price, exit_fee)

            self._positions.pop(position_id, None)
            sym_list = self._open_positions_by_symbol.get(pos.symbol, [])
            if position_id in sym_list:
                sym_list.remove(position_id)
            self._closed_positions.append(pos)

        publish_event(
            SIM_PLACEHOLDER_UPDATED,
            {"positionId": position_id, "state": POS_CLOSED,
             "realisedPnl": pnl, "researchOnly": True},
            idempotency_key=f"sim_close_{position_id}",
        )
        return pnl

    def _compute_fill_price_for_close(self, pos: SimPosition, mark_price: float) -> float:
        spread_half = mark_price * self._config["spread_bps"] / 10_000.0
        slippage = mark_price * self._config["slippage_market_bps"] / 10_000.0
        if pos.side == SIDE_LONG:
            fill = mark_price - spread_half - slippage
        else:
            fill = mark_price + spread_half + slippage
        return round(fill, self._config["price_precision"])

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending/partial order."""
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                return False
            if order.state not in (STATE_PENDING, STATE_PARTIAL):
                return False
            order.state = STATE_CANCELLED
            order.updated_at_ms = int(time.time() * 1000)
            self._order_history.append(order)
            self._orders.pop(order_id, None)
        return True

    def activate_kill_switch(self, reason: str = "operator") -> None:
        """Halt all new order submissions."""
        self._kill_switch = True
        logger.warning("[sim] KILL SWITCH activated: %s", reason)

    def deactivate_kill_switch(self) -> None:
        self._kill_switch = False
        logger.info("[sim] kill switch deactivated")

    # ── Read accessors ─────────────────────────────────────────────────────────

    def get_order(self, order_id: str) -> SimOrder | None:
        with self._lock:
            return self._orders.get(order_id)

    def list_orders(
        self,
        symbol: str | None = None,
        state: str | None = None,
        include_history: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._lock:
            active = list(self._orders.values())
            history = list(self._order_history) if include_history else []
        all_orders = active + history
        if symbol:
            all_orders = [o for o in all_orders if o.symbol == symbol]
        if state:
            all_orders = [o for o in all_orders if o.state == state]
        all_orders.sort(key=lambda o: o.created_at_ms, reverse=True)
        return [o.to_dict() for o in all_orders[:limit]]

    def list_open_positions(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            positions = list(self._positions.values())
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        return [p.to_dict() for p in positions]

    def list_closed_positions(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._lock:
            positions = list(self._closed_positions)
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        return [p.to_dict() for p in positions[-limit:]]

    def total_unrealised_pnl(self) -> float:
        with self._lock:
            return sum(p.unrealised_pnl for p in self._positions.values())

    def total_realised_pnl(self) -> float:
        with self._lock:
            return sum(
                (p.realised_pnl or 0.0)
                for p in self._closed_positions
            )

    def status(self) -> dict[str, Any]:
        with self._lock:
            open_pos = len(self._positions)
            closed_pos = len(self._closed_positions)
            active_orders = len(self._orders)
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "killSwitch": self._kill_switch,
            "totalOrders": self._total_orders,
            "totalFills": self._total_fills,
            "totalRejects": self._total_rejects,
            "activeOrders": active_orders,
            "openPositions": open_pos,
            "closedPositions": closed_pos,
            "unrealisedPnl": self.total_unrealised_pnl(),
            "realisedPnl": self.total_realised_pnl(),
            "config": {
                k: v for k, v in self._config.items()
                if k in ("spread_bps", "slippage_market_bps", "taker_fee_bps",
                          "maker_fee_bps", "default_leverage", "max_leverage")
            },
            "startedAtMs": self._started_at_ms,
            "generatedAt": int(time.time() * 1000),
        }

    def reset(self) -> None:
        """Reset simulator state (for test / replay use)."""
        with self._lock:
            self._orders.clear()
            self._order_history.clear()
            self._positions.clear()
            self._open_positions_by_symbol.clear()
            self._closed_positions.clear()
            self._kill_switch = False
            self._total_orders = 0
            self._total_fills = 0
            self._total_rejects = 0
            self._started_at_ms = int(time.time() * 1000)
        logger.info("[sim] exchange state reset")


# ── Singleton ─────────────────────────────────────────────────────────────────
_SIM: SimulatedExchange | None = None
_SIM_LOCK = threading.Lock()


def get_simulator(config: dict[str, Any] | None = None) -> SimulatedExchange:
    global _SIM
    with _SIM_LOCK:
        if _SIM is None:
            _SIM = SimulatedExchange(config=config)
            logger.info("[sim] SimulatedExchange initialised (researchOnly=true)")
        return _SIM


def reset_simulator() -> None:
    global _SIM
    with _SIM_LOCK:
        if _SIM is not None:
            _SIM.reset()
        else:
            _SIM = SimulatedExchange()
    logger.info("[sim] simulator reset")
