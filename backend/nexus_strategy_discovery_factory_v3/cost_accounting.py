"""Full cost accounting for discovery candidates — delegates fee/spread/slip/funding
to canonical CostModelContract; adds market-impact approximation explicitly.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any

from backend.nexus_execution.cost_model import (
    COST_MODEL_VERSION,
    DEFAULT_SLIPPAGE_BPS,
    DEFAULT_SPREAD_BPS,
    DEFAULT_TAKER_FEE,
    cancel_replace_component,
    compose_cost_bridge,
    funding_unavailable_buffer,
    leg_costs_for_notional,
    partial_fill_component,
)
from backend.nexus_strategy_discovery_factory_v3.constants import REQUIRED_COST_COMPONENTS


def _d(x: float | int | str | Decimal) -> Decimal:
    return Decimal(str(x))


def market_impact_approximation(
    *,
    notional: Decimal,
    impact_bps: Decimal,
) -> Decimal:
    """Conservative visible-depth impact proxy (research approximation).

    Not part of CostBridge identity; reported as an explicit required component.
    """
    if impact_bps <= 0 or notional <= 0:
        return Decimal(0)
    return abs(notional) * impact_bps / Decimal("10000")


def code_checksum(module_blob: str) -> str:
    return hashlib.sha256(module_blob.encode()).hexdigest()


def parameter_checksum(params: dict[str, Any]) -> str:
    blob = "|".join(f"{k}={params[k]!r}" for k in sorted(params))
    return hashlib.sha256(blob.encode()).hexdigest()


def account_trade_costs(
    *,
    side: str,  # LONG | SHORT
    qty: Decimal,
    entry_price: Decimal,
    exit_price: Decimal,
    spread_bps: Decimal | None = None,
    slippage_bps: Decimal | None = None,
    impact_bps: Decimal | None = None,
    funding_rate: Decimal | None = None,
    extra_fills: int = 0,
    cancel_replace_cycles: int = 0,
) -> dict[str, Any]:
    """Compute gross, all required cost components, and net after full costs."""
    notional = abs(qty * entry_price)
    sp = spread_bps if spread_bps is not None else DEFAULT_SPREAD_BPS
    sl = slippage_bps if slippage_bps is not None else DEFAULT_SLIPPAGE_BPS
    imp = impact_bps if impact_bps is not None else Decimal("2.0")

    entry = leg_costs_for_notional(
        notional=notional,
        is_taker=True,
        fee_rate=DEFAULT_TAKER_FEE,
        spread_bps=sp,
        slippage_bps=sl,
    )
    exit_ = leg_costs_for_notional(
        notional=notional,
        is_taker=True,
        fee_rate=DEFAULT_TAKER_FEE,
        spread_bps=sp,
        slippage_bps=sl,
    )
    if funding_rate is None:
        funding = funding_unavailable_buffer(notional=notional)
    else:
        funding = abs(notional * funding_rate)
    partial = partial_fill_component(extra_fills=extra_fills)
    cancel = cancel_replace_component(cycles=cancel_replace_cycles)
    impact = market_impact_approximation(notional=notional, impact_bps=imp)

    bridge = compose_cost_bridge(
        side=side,
        qty=qty,
        entry_price=entry_price,
        exit_price=exit_price,
        entry_fee=entry["fee"],
        exit_fee=exit_["fee"],
        entry_spread=entry["spread_cost"],
        exit_spread=exit_["spread_cost"],
        entry_slippage=entry["slippage_cost"],
        exit_slippage=exit_["slippage_cost"],
        funding=funding,
        partial_fill=partial,
        cancel_replace=cancel,
    )
    # Full research net subtracts market-impact approximation after CostBridge.
    net_after_full_costs = bridge.net_pnl - impact
    components = {
        "entry_fee": bridge.entry_fee,
        "exit_fee": bridge.exit_fee,
        "spread_cost": bridge.spread_cost,
        "slippage_cost": bridge.slippage_cost,
        "funding_cost": bridge.funding_cost,
        "partial_fill_cost": bridge.partial_fill_cost,
        "cancel_replace_cost": bridge.cancel_replace_cost,
        "market_impact_approximation": impact,
    }
    missing = [k for k in REQUIRED_COST_COMPONENTS if k not in components]
    if missing:
        raise AssertionError(f"missing_cost_components={missing}")
    return {
        "cost_model_version": COST_MODEL_VERSION,
        "cost_authority": "backend.nexus_execution.cost_model",
        "gross_pnl": bridge.gross_pnl,
        "cost_bridge_net_pnl": bridge.net_pnl,
        "net_pnl": net_after_full_costs,
        "cost_components": {k: format(v, "f") for k, v in components.items()},
        "cost_components_decimal": components,
        "notional": format(notional, "f"),
        "market_impact_outside_cost_bridge": True,
        "cost_bridge_verified": True,
    }


def aggregate_costs(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        zeros = {k: "0" for k in REQUIRED_COST_COMPONENTS}
        return {
            "gross_pnl": "0",
            "net_pnl": "0",
            "cost_components": zeros,
            "trade_count": 0,
        }
    gross = sum((_d(t["gross_pnl"]) for t in trades), Decimal(0))
    net = sum((_d(t["net_pnl"]) for t in trades), Decimal(0))
    comps: dict[str, Decimal] = {k: Decimal(0) for k in REQUIRED_COST_COMPONENTS}
    for t in trades:
        cc = t.get("_cost_components_decimal") or t.get("cost_components_decimal")
        if not cc:
            cc = {k: _d(t["cost_components"][k]) for k in REQUIRED_COST_COMPONENTS}
        for k in REQUIRED_COST_COMPONENTS:
            comps[k] += _d(cc[k])
    return {
        "gross_pnl": format(gross, "f"),
        "net_pnl": format(net, "f"),
        "cost_components": {k: format(v, "f") for k, v in comps.items()},
        "trade_count": len(trades),
        "cost_model_version": COST_MODEL_VERSION,
    }
