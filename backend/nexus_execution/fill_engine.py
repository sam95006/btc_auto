"""Deterministic conservative fill engine.

Rules:

* MARKET orders always fill immediately at the far side of the spread
  (buy = ask, sell = bid). Taker only.
* LIMIT orders require the bar to trade *through* the limit price by at least
  one full tick. Touch alone is insufficient. Filled at limit_price. Maker
  side.
* STOP_MARKET / TAKE_PROFIT_MARKET orders arm only when the bar's mark price
  path proves the trigger has been hit by at least one tick on the correct
  side. Once armed, the fill uses the market bid/ask at trigger. Taker.
* When a bar covers both a stop *and* a take-profit for the same position we
  refuse to guess — the order is marked BLOCKED_AMBIGUOUS and no fill occurs
  (adverse-first policy).
* Time-in-force IOC cancels the remainder immediately if not fully filled.
* Time-in-force FOK rejects the whole order if it cannot be fully filled.
* Any order past its ``expires_at_bar`` is transitioned to EXPIRED with
  zero fills.

The engine emits :class:`~contracts.FillEvent` records — never trade objects
directly. Trade construction happens in the simulator once entry and exit
records are both terminal.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any

from backend.nexus_execution.contracts import FillEvent, InstrumentSpec, OrderRecord


@dataclass(frozen=True, slots=True)
class BarContext:
    """One bar of market data. All fields Decimals for exact accounting."""

    bar_index: int
    open_price: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    mark_price: Decimal
    index_price: Decimal | None
    bid: Decimal
    ask: Decimal
    mark_price_age_ms: int = 0
    same_bar_stop: Decimal | None = None
    same_bar_target: Decimal | None = None


STALE_MARK_MS_THRESHOLD = 5_000  # 5s


@dataclass(frozen=True, slots=True)
class FillOutcome:
    """Result of attempting to fill an order against a bar."""

    status: str  # FILLED | PARTIALLY_FILLED | UNFILLED | EXPIRED | REJECTED | BLOCKED_AMBIGUOUS
    fills: tuple[FillEvent, ...] = ()
    reject_reason: str | None = None
    is_taker: bool = True


def _mk_fill_id(order_id: str, bar_index: int, seq: int) -> str:
    h = hashlib.sha256(f"{order_id}|{bar_index}|{seq}".encode()).hexdigest()
    return h[:24]


def _same_bar_ambiguous(bar: BarContext) -> bool:
    if bar.same_bar_stop is None or bar.same_bar_target is None:
        return False
    lo, hi = bar.low, bar.high
    hit_stop = lo <= bar.same_bar_stop <= hi
    hit_target = lo <= bar.same_bar_target <= hi
    return hit_stop and hit_target


def _validate_bar_prices(bar: BarContext) -> str | None:
    if bar.mark_price is None or bar.mark_price <= 0:
        return "MARK_PRICE_MISSING"
    if bar.index_price is None:
        return "INDEX_PRICE_MISSING"
    if bar.mark_price_age_ms > STALE_MARK_MS_THRESHOLD:
        return "STALE_MARK_PRICE"
    if bar.bid <= 0 or bar.ask <= 0 or bar.ask < bar.bid:
        return "INVALID_QUOTE"
    return None


def _fill_price_for_market(order: OrderRecord, bar: BarContext) -> Decimal:
    return bar.ask if order.intent.side == "BUY" else bar.bid


def _limit_trade_through(order: OrderRecord, bar: BarContext, tick: Decimal) -> bool:
    price = order.intent.price
    assert price is not None
    if order.intent.side == "BUY":
        return bar.low <= (price - tick)
    return bar.high >= (price + tick)


def _stop_triggered(order: OrderRecord, bar: BarContext, tick: Decimal) -> bool:
    stop = order.intent.stop_price
    assert stop is not None
    if order.intent.order_type == "STOP_MARKET":
        # sell stop below (protect long) or buy stop above (protect short)
        if order.intent.side == "SELL":
            return bar.low <= (stop - tick) or bar.mark_price <= (stop - tick)
        return bar.high >= (stop + tick) or bar.mark_price >= (stop + tick)
    # TAKE_PROFIT_MARKET: sell TP above long, buy TP below short (mirror)
    if order.intent.side == "SELL":
        return bar.high >= (stop + tick) or bar.mark_price >= (stop + tick)
    return bar.low <= (stop - tick) or bar.mark_price <= (stop - tick)


def try_fill(
    order: OrderRecord,
    spec: InstrumentSpec,
    bar: BarContext,
    *,
    partial_ratio: Decimal | None = None,
) -> FillOutcome:
    """Attempt to fill ``order`` against ``bar``.

    Returns a :class:`FillOutcome`. The caller is responsible for advancing
    the order's state based on the outcome — the engine never mutates state
    directly to keep the state machine centralised.
    """
    if order.state in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}:
        return FillOutcome(status=order.state)

    if order.intent.expires_at_bar is not None and bar.bar_index > order.intent.expires_at_bar:
        return FillOutcome(status="EXPIRED")

    bar_error = _validate_bar_prices(bar)
    if bar_error is not None:
        return FillOutcome(status="REJECTED", reject_reason=bar_error)

    if _same_bar_ambiguous(bar):
        return FillOutcome(
            status="BLOCKED_AMBIGUOUS",
            reject_reason="SAME_BAR_STOP_TARGET_ADVERSE_FIRST",
        )

    is_taker = True
    fill_price: Decimal | None = None
    ot = order.intent.order_type

    if ot == "MARKET":
        fill_price = _fill_price_for_market(order, bar)
    elif ot == "LIMIT":
        if _limit_trade_through(order, bar, spec.tick_size):
            fill_price = order.intent.price
            is_taker = False
    elif ot in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
        if _stop_triggered(order, bar, spec.tick_size):
            fill_price = bar.ask if order.intent.side == "BUY" else bar.bid
    else:
        return FillOutcome(status="REJECTED", reject_reason="UNSUPPORTED_ORDER_TYPE")

    if fill_price is None:
        # Handle time-in-force for orders that could not fill this bar.
        if order.intent.time_in_force == "IOC":
            return FillOutcome(status="EXPIRED", reject_reason="IOC_NOT_FILLED")
        if order.intent.time_in_force == "FOK":
            return FillOutcome(status="REJECTED", reject_reason="FOK_NOT_FILLED")
        return FillOutcome(status="UNFILLED", is_taker=is_taker)

    remaining = order.intent.qty - order.filled_qty
    fill_qty = remaining
    if partial_ratio is not None and Decimal(0) < partial_ratio < Decimal(1):
        raw = (order.intent.qty * partial_ratio)
        units = (raw / spec.lot_size).to_integral_value(rounding=ROUND_DOWN)
        candidate = units * spec.lot_size
        if candidate <= 0:
            return FillOutcome(status="UNFILLED", is_taker=is_taker)
        if candidate > remaining:
            candidate = remaining
        fill_qty = candidate

    if order.intent.time_in_force == "FOK" and fill_qty < order.intent.qty:
        return FillOutcome(status="REJECTED", reject_reason="FOK_PARTIAL_NOT_ALLOWED")

    fee_rate = spec.taker_fee if is_taker else spec.maker_fee
    fee = fill_price * fill_qty * fee_rate
    fill = FillEvent(
        order_id=order.order_id,
        fill_id=_mk_fill_id(order.order_id, bar.bar_index, len(order.fills)),
        qty=fill_qty,
        price=fill_price,
        fee=fee,
        is_taker=is_taker,
        bar_index=bar.bar_index,
    )

    new_filled = order.filled_qty + fill_qty
    if new_filled >= order.intent.qty:
        status = "FILLED"
    else:
        status = "PARTIALLY_FILLED"
        if order.intent.time_in_force == "IOC":
            # remainder cancelled after partial fill under IOC
            pass  # simulator records IOC cancel of remainder; outcome reports fill only
    return FillOutcome(status=status, fills=(fill,), is_taker=is_taker)
