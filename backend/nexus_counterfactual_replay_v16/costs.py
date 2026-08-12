"""Cost/slippage accounting via canonical CostBridge (consumer only)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.nexus_cost_sensitivity.cost_consumer import account_round_trip, assert_canonical_authority


def apply_round_trip_costs(
    *,
    side: str,
    size: float,
    entry_price: float,
    exit_price: float,
    slippage_bps: float | None = None,
) -> dict[str, Any]:
    """Include fee/spread/slippage; never redefine CostBridge formulas."""
    authority = assert_canonical_authority()
    bridge_side = "LONG" if side.upper() in {"LONG", "BUY"} else "SHORT"
    result = account_round_trip(
        side=bridge_side,
        qty=Decimal(str(abs(size))),
        entry_price=Decimal(str(entry_price)),
        exit_price=Decimal(str(exit_price)),
        maker_taker_mix=1.0,
        slippage_bps=Decimal(str(slippage_bps)) if slippage_bps is not None else None,
    )
    comps = result["cost_components_decimal"]
    fee_cost = comps["entry_fee"] + comps["exit_fee"]
    return {
        "gross_pnl": float(result["gross_pnl"]),
        "net_pnl": float(result["net_pnl"]),
        "cost_total": float(result["total_cost"]),
        "fee_cost": float(fee_cost),
        "spread_cost": float(comps["spread_cost"]),
        "slippage_cost": float(comps["slippage_cost"]),
        "cost_included": True,
        "canonical_cost_authority": authority["canonical_cost_authority"],
        "canonical_cost_formula_mutated": False,
    }
