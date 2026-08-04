"""Deterministic cost model with exact-decimal accounting.

Every cost component is computed as a :class:`decimal.Decimal` so the cost
bridge equation

    gross_pnl - entry_fee - exit_fee - spread_cost - slippage_cost
              - funding_cost - partial_fill_cost - cancel_replace_cost
    == net_pnl

holds exactly, not within a floating-point tolerance.

Cost components:
  * ``entry_fee``            fee for opening leg (maker or taker)
  * ``exit_fee``             fee for closing leg (maker or taker)
  * ``spread_cost``          notional * spread_bps
  * ``slippage_cost``        notional * slippage_bps for taker legs only
  * ``funding_cost``         signed; positive = debit, negative = credit
  * ``partial_fill_cost``    fixed penalty per additional fill event
  * ``cancel_replace_cost``  fixed penalty per cancel/replace cycle
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from backend.nexus_execution.contracts import CostBridge, InstrumentSpec

BPS = Decimal("10000")

# Founder-conservative defaults (linear scale, no exchange-specific tiering).
DEFAULT_SPREAD_BPS = Decimal("1.0")
DEFAULT_SLIPPAGE_BPS = Decimal("2.0")
DEFAULT_PARTIAL_FILL_PENALTY = Decimal("0.005")   # USDT per extra fill event
DEFAULT_CANCEL_REPLACE_PENALTY = Decimal("0.01")  # USDT per cancel/replace cycle

COST_MODEL_VERSION = "founder-conservative-v1-1-2026-08-05"


def _bps_cost(notional: Decimal, bps: Decimal) -> Decimal:
    return (notional * bps / BPS)


def entry_leg_cost(
    spec: InstrumentSpec,
    *,
    price: Decimal,
    qty: Decimal,
    is_taker: bool,
    spread_bps: Decimal = DEFAULT_SPREAD_BPS,
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return ``(fee, spread, slippage)`` for the opening leg."""
    notional = price * qty
    fee_rate = spec.taker_fee if is_taker else spec.maker_fee
    fee = notional * fee_rate
    spread = _bps_cost(notional, spread_bps)
    slippage = _bps_cost(notional, slippage_bps) if is_taker else Decimal(0)
    return (fee, spread, slippage)


def exit_leg_cost(
    spec: InstrumentSpec,
    *,
    price: Decimal,
    qty: Decimal,
    is_taker: bool,
    spread_bps: Decimal = DEFAULT_SPREAD_BPS,
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return ``(fee, spread, slippage)`` for the closing leg (same shape)."""
    return entry_leg_cost(
        spec,
        price=price,
        qty=qty,
        is_taker=is_taker,
        spread_bps=spread_bps,
        slippage_bps=slippage_bps,
    )


def funding_component(
    *,
    notional: Decimal,
    funding_rate: Decimal,
    intervals: int,
) -> Decimal:
    """Signed funding: positive means the position owes funding (debit)."""
    if intervals <= 0 or funding_rate == 0:
        return Decimal(0)
    return notional * funding_rate * Decimal(intervals)


def partial_fill_component(*, extra_fills: int) -> Decimal:
    """Penalty for splitting the notional across multiple fills."""
    if extra_fills <= 0:
        return Decimal(0)
    return DEFAULT_PARTIAL_FILL_PENALTY * Decimal(extra_fills)


def cancel_replace_component(*, cycles: int) -> Decimal:
    if cycles <= 0:
        return Decimal(0)
    return DEFAULT_CANCEL_REPLACE_PENALTY * Decimal(cycles)


def compose_cost_bridge(
    *,
    side: str,  # LONG | SHORT
    qty: Decimal,
    entry_price: Decimal,
    exit_price: Decimal,
    entry_fee: Decimal,
    exit_fee: Decimal,
    entry_spread: Decimal,
    exit_spread: Decimal,
    entry_slippage: Decimal,
    exit_slippage: Decimal,
    funding: Decimal,
    partial_fill: Decimal,
    cancel_replace: Decimal,
) -> CostBridge:
    """Assemble an :class:`~contracts.CostBridge` from atomic legs.

    ``side`` uses LONG/SHORT (position semantics), not BUY/SELL.
    """
    sign = Decimal(1) if side.upper() == "LONG" else Decimal(-1)
    gross_pnl = (exit_price - entry_price) * qty * sign
    spread_cost = entry_spread + exit_spread
    slippage_cost = entry_slippage + exit_slippage
    net_pnl = (
        gross_pnl
        - entry_fee
        - exit_fee
        - spread_cost
        - slippage_cost
        - funding
        - partial_fill
        - cancel_replace
    )
    return CostBridge(
        gross_pnl=gross_pnl,
        entry_fee=entry_fee,
        exit_fee=exit_fee,
        spread_cost=spread_cost,
        slippage_cost=slippage_cost,
        funding_cost=funding,
        partial_fill_cost=partial_fill,
        cancel_replace_cost=cancel_replace,
        net_pnl=net_pnl,
    )


def sum_decimals(values: Iterable[Decimal]) -> Decimal:
    total = Decimal(0)
    for v in values:
        total = total + v
    return total
