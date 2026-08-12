"""Instrument validation helpers.

Every quantity/price the simulator handles is first checked against the
instrument's tick size, lot size, minimum notional and instrument status.

All rounding uses :func:`decimal.Decimal.quantize` with ``ROUND_DOWN`` to
avoid ever creating a synthetic size larger than requested.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import Any

from backend.nexus_execution.contracts import InstrumentSpec


class InstrumentViolation(ValueError):
    """Raised (or returned via reason code) when an intent violates instrument rules."""


DEFAULT_INSTRUMENTS: dict[str, InstrumentSpec] = {
    "BTCUSDT": InstrumentSpec(
        symbol="BTCUSDT",
        tick_size=Decimal("0.1"),
        lot_size=Decimal("0.001"),
        min_notional=Decimal("5"),
    ),
    "ETHUSDT": InstrumentSpec(
        symbol="ETHUSDT",
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.01"),
        min_notional=Decimal("5"),
    ),
    "SOLUSDT": InstrumentSpec(
        symbol="SOLUSDT",
        tick_size=Decimal("0.001"),
        lot_size=Decimal("0.1"),
        min_notional=Decimal("5"),
    ),
    "XRPUSDT": InstrumentSpec(
        symbol="XRPUSDT",
        tick_size=Decimal("0.0001"),
        lot_size=Decimal("1"),
        min_notional=Decimal("5"),
    ),
    "HALTED_TEST": InstrumentSpec(
        symbol="HALTED_TEST",
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.001"),
        min_notional=Decimal("5"),
        status="HALTED",
    ),
}


def snap_qty(qty: Decimal, lot: Decimal) -> Decimal:
    """Snap ``qty`` down to the nearest multiple of ``lot``.

    Guarantees:
      * result <= qty
      * result % lot == 0 (within Decimal precision)
    """
    if lot == 0:
        return qty
    units = (qty / lot).to_integral_value(rounding=ROUND_DOWN)
    return units * lot


def snap_price(price: Decimal, tick: Decimal) -> Decimal:
    if tick == 0:
        return price
    units = (price / tick).to_integral_value(rounding=ROUND_DOWN)
    return units * tick


def is_on_tick(price: Decimal, tick: Decimal) -> bool:
    if tick == 0:
        return True
    return (price / tick) == (price / tick).to_integral_value(rounding=ROUND_DOWN)


def is_on_lot(qty: Decimal, lot: Decimal) -> bool:
    if lot == 0:
        return True
    return (qty / lot) == (qty / lot).to_integral_value(rounding=ROUND_DOWN)


def validate_intent(
    spec: InstrumentSpec,
    *,
    qty: Decimal,
    price: Decimal | None,
    stop_price: Decimal | None,
    mark_price: Decimal,
    order_type: str,
) -> dict[str, Any] | None:
    """Return ``None`` on success or a reject-reason dict on failure."""
    if not spec.is_tradable():
        return {"reason": "INSTRUMENT_HALTED", "detail": spec.status}
    if qty <= 0:
        return {"reason": "QUANTITY_NON_POSITIVE"}
    if not is_on_lot(qty, spec.lot_size):
        return {
            "reason": "QUANTITY_STEP_VIOLATION",
            "detail": {"qty": format(qty, "f"), "lot_size": format(spec.lot_size, "f")},
        }
    reference_price = None
    if order_type == "LIMIT":
        if price is None or price <= 0:
            return {"reason": "LIMIT_PRICE_MISSING"}
        if not is_on_tick(price, spec.tick_size):
            return {
                "reason": "TICK_SIZE_VIOLATION",
                "detail": {"price": format(price, "f"), "tick": format(spec.tick_size, "f")},
            }
        reference_price = price
    elif order_type in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
        if stop_price is None or stop_price <= 0:
            return {"reason": "STOP_PRICE_MISSING"}
        if not is_on_tick(stop_price, spec.tick_size):
            return {
                "reason": "TICK_SIZE_VIOLATION",
                "detail": {"stop_price": format(stop_price, "f"), "tick": format(spec.tick_size, "f")},
            }
        reference_price = mark_price
    else:  # MARKET
        reference_price = mark_price

    if reference_price is None or reference_price <= 0:
        return {"reason": "PRICE_MISSING_FOR_NOTIONAL"}

    notional = qty * reference_price
    if notional < spec.min_notional:
        return {
            "reason": "MIN_NOTIONAL_VIOLATION",
            "detail": {"notional": format(notional, "f"), "min": format(spec.min_notional, "f")},
        }
    return None
