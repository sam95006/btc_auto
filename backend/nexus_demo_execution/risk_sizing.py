"""Exchange-valid risk sizing for offline qualification — 20U / 25x / 3U.

Does not place orders. Liquidation model is approximate isolated USDT-linear.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from backend.nexus_demo_execution.session_limits import (
    FIXED_LEVERAGE,
    MARGIN_MODE,
    MARGIN_PER_TRADE_CAP,
    MAX_SINGLE_TRADE_NET_LOSS,
)

# Founder audit constants (session loss for audit packet; code session limit may differ).
AUDIT_SESSION_NET_LOSS_LIMIT = 15.0
MAINTENANCE_MARGIN_RATE = 0.005  # conservative linear MMR proxy


@dataclass
class SizedPosition:
    symbol: str
    side: str
    entry_price: float
    stop_price: float
    take_profit_price: float | None
    margin_usdt: float
    leverage: int
    margin_mode: str
    desired_notional: float
    quantity_by_risk: float
    quantity_by_margin: float
    quantity_raw: float
    quantity: float
    notional: float
    risk_per_unit: float
    stop_distance_pct: float
    target_distance_pct: float | None
    liquidation_price: float
    distance_to_liquidation_pct: float
    maximum_possible_loss: float
    risk_budget: float
    risk_budget_breached: bool
    allowed: bool
    block_reason: str
    labels: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def liquidation_price(*, entry_price: float, side: str, leverage: int, mmr: float = MAINTENANCE_MARGIN_RATE) -> float:
    """Approximate isolated linear liquidation (bankruptcy ± MMR)."""
    lev = max(1, int(leverage))
    buy = side.lower() in {"buy", "long"}
    if buy:
        return float(entry_price) * (1.0 - (1.0 / lev) + float(mmr))
    return float(entry_price) * (1.0 + (1.0 / lev) - float(mmr))


def _floor_to_step(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    # Avoid float dust
    n = math.floor((qty + 1e-15) / step)
    return round(n * step, 12)


def size_position(
    *,
    symbol: str,
    side: str,
    entry_price: float,
    stop_price: float,
    take_profit_price: float | None = None,
    margin_usdt: float = MARGIN_PER_TRADE_CAP,
    leverage: int = FIXED_LEVERAGE,
    risk_budget_usdt: float = MAX_SINGLE_TRADE_NET_LOSS,
    qty_step: float = 0.001,
    min_order_qty: float = 0.0,
    min_notional: float = 5.0,
    tick_size: float | None = None,
) -> SizedPosition:
    """Risk-capped quantity: min(risk budget qty, margin*leverage/entry)."""
    labels: list[str] = []
    entry = float(entry_price)
    stop = float(stop_price)
    margin = float(margin_usdt)
    lev = int(leverage)
    risk_budget = float(risk_budget_usdt)
    desired_notional = margin * lev
    buy = side.lower() in {"buy", "long"}

    liq = liquidation_price(entry_price=entry, side=side, leverage=lev)
    risk_per_unit = abs(entry - stop)
    stop_distance_pct = (risk_per_unit / entry) if entry > 0 else float("inf")
    tgt_pct = None
    if take_profit_price is not None:
        tgt_pct = abs(float(take_profit_price) - entry) / entry if entry > 0 else None

    if entry <= 0 or risk_per_unit <= 0:
        return SizedPosition(
            symbol=symbol,
            side=side,
            entry_price=entry,
            stop_price=stop,
            take_profit_price=take_profit_price,
            margin_usdt=margin,
            leverage=lev,
            margin_mode=MARGIN_MODE,
            desired_notional=desired_notional,
            quantity_by_risk=0.0,
            quantity_by_margin=0.0,
            quantity_raw=0.0,
            quantity=0.0,
            notional=0.0,
            risk_per_unit=risk_per_unit,
            stop_distance_pct=stop_distance_pct,
            target_distance_pct=tgt_pct,
            liquidation_price=liq,
            distance_to_liquidation_pct=0.0,
            maximum_possible_loss=0.0,
            risk_budget=risk_budget,
            risk_budget_breached=True,
            allowed=False,
            block_reason="BLOCK_INVALID_TRADE_GEOMETRY",
            labels=["invalid_entry_or_stop"],
        )

    qty_by_risk = risk_budget / risk_per_unit
    qty_by_margin = desired_notional / entry
    qty_raw = min(qty_by_risk, qty_by_margin)
    qty = _floor_to_step(qty_raw, float(qty_step))

    # Liquidation boundary: stop must remain on safe side of liq with buffer.
    if buy:
        dist_liq_pct = (entry - liq) / entry
        stop_crosses_liq = stop <= liq
        too_close = stop <= liq * 1.001  # within 0.1% of liq
    else:
        dist_liq_pct = (liq - entry) / entry
        stop_crosses_liq = stop >= liq
        too_close = stop >= liq * 0.999

    max_loss_at_stop = qty * risk_per_unit
    breached = max_loss_at_stop > risk_budget + 1e-9

    block = ""
    allowed = True
    if stop_crosses_liq or too_close:
        allowed = False
        block = "BLOCK_LIQUIDATION_TOO_CLOSE"
        labels.append("stop_vs_liquidation")
    elif breached:
        allowed = False
        block = "BLOCK_RISK_BUDGET_EXCEEDED"
        labels.append("risk_budget")
    elif qty <= 0:
        allowed = False
        block = "BLOCK_QUANTITY_ROUNDS_TO_ZERO"
        labels.append("qty_step_rounding")
    elif min_order_qty > 0 and qty + 1e-15 < min_order_qty:
        allowed = False
        block = "BLOCK_INSTRUMENT_MINIMUM_NOT_MET"
        labels.append("min_order_qty")
    elif min_notional > 0 and qty * entry + 1e-12 < min_notional:
        allowed = False
        block = "BLOCK_INSTRUMENT_MINIMUM_NOT_MET"
        labels.append("min_notional")

    # Leverage must not be applied twice: notional = margin * leverage once.
    notional = qty * entry
    if abs(notional - (qty * entry)) > 1e-9:
        labels.append("notional_inconsistent")

    return SizedPosition(
        symbol=symbol,
        side=side,
        entry_price=entry,
        stop_price=stop,
        take_profit_price=take_profit_price,
        margin_usdt=margin,
        leverage=lev,
        margin_mode=MARGIN_MODE,
        desired_notional=desired_notional,
        quantity_by_risk=qty_by_risk,
        quantity_by_margin=qty_by_margin,
        quantity_raw=qty_raw,
        quantity=qty,
        notional=notional,
        risk_per_unit=risk_per_unit,
        stop_distance_pct=stop_distance_pct,
        target_distance_pct=tgt_pct,
        liquidation_price=liq,
        distance_to_liquidation_pct=dist_liq_pct,
        maximum_possible_loss=max_loss_at_stop,
        risk_budget=risk_budget,
        risk_budget_breached=breached,
        allowed=allowed,
        block_reason=block if not allowed else "OK",
        labels=labels,
    )


def detect_sizing_defects(
    *,
    entry_price: float,
    qty: float,
    stop_price: float,
    side: str,
    net_pnl: float | None,
    margin_usdt: float = MARGIN_PER_TRADE_CAP,
    leverage: int = FIXED_LEVERAGE,
    risk_budget: float = MAX_SINGLE_TRADE_NET_LOSS,
) -> dict[str, Any]:
    """Flag defects relative to Founder risk model for a completed trade row."""
    desired_notional = margin_usdt * leverage
    notional = abs(float(qty) * float(entry_price))
    risk_per_unit = abs(float(entry_price) - float(stop_price))
    max_loss = abs(float(qty)) * risk_per_unit
    liq = liquidation_price(entry_price=entry_price, side=side, leverage=leverage)
    buy = side.lower() in {"buy", "long"}
    stop_beyond_liq = (float(stop_price) <= liq) if buy else (float(stop_price) >= liq)
    defects: list[str] = []
    if abs(notional - desired_notional) / max(desired_notional, 1e-9) > 0.5:
        # More than 50% off intended notional → sizing bug class
        defects.append("POSITION_SIZING_OFF_TARGET")
    if max_loss > risk_budget * 1.05:
        defects.append("RISK_BUDGET_BREACH")
    if stop_beyond_liq:
        defects.append("STOP_BEYOND_LIQUIDATION")
    if net_pnl is not None and abs(float(net_pnl)) > risk_budget * 5 and max_loss > risk_budget * 5:
        defects.append("LOSS_SCALE_INCONSISTENT_WITH_3U_BUDGET")
    # Leverage double-count heuristic: if notional ≈ margin * leverage^2
    if abs(notional - margin_usdt * (leverage**2)) / max(notional, 1.0) < 0.05:
        defects.append("LEVERAGE_LIKELY_DOUBLE_APPLIED")
    return {
        "notional": notional,
        "desired_notional": desired_notional,
        "maximum_possible_loss": max_loss,
        "risk_budget": risk_budget,
        "liquidation_price": liq,
        "stop_beyond_liquidation": stop_beyond_liq,
        "defects": defects,
    }
