"""Turnover and cost sensitivity probes (development / synthetic only)."""
from __future__ import annotations

from typing import Any, Mapping

from backend.nexus_research_validation.constants import (
    REQUIRED_COST_COMPONENTS,
    TURNOVER_COST_RATIO_DESTROY,
)


def cost_turnover_sensitivity(
    *,
    gross_pnl: float,
    net_pnl: float,
    cost_components: Mapping[str, float | str],
    turnover_notional: float,
) -> dict[str, Any]:
    comps = {k: float(cost_components.get(k, 0) or 0) for k in REQUIRED_COST_COMPONENTS}
    # Ensure turnover_cost present
    if "turnover_cost" not in cost_components:
        comps["turnover_cost"] = abs(float(turnover_notional)) * 0.0002
    total_cost = sum(max(0.0, v) for v in comps.values())
    gross = float(gross_pnl)
    net = float(net_pnl)
    turnover_cost = float(comps.get("turnover_cost") or 0.0)
    turnover_ratio = turnover_cost / max(abs(gross), 1e-9) if gross != 0 else (
        float("inf") if turnover_cost > 0 else 0.0
    )

    cost_destroyed = gross > 0 and net <= 0
    turnover_destroyed = (
        gross > 0 and turnover_ratio >= TURNOVER_COST_RATIO_DESTROY
    ) or (gross > 0 and net <= 0 and turnover_cost >= abs(gross) * 0.5)

    missing = [k for k in REQUIRED_COST_COMPONENTS if k not in comps]
    return {
        "gross_pnl": gross,
        "net_pnl": net,
        "total_cost": total_cost,
        "cost_components": comps,
        "turnover_notional": float(turnover_notional),
        "turnover_cost": turnover_cost,
        "turnover_cost_to_gross_ratio": (
            turnover_ratio if turnover_ratio != float("inf") else None
        ),
        "cost_destroyed": cost_destroyed,
        "turnover_destroyed": turnover_destroyed,
        "destroyed": cost_destroyed or turnover_destroyed,
        "missing_cost_components": missing,
        "required_cost_components": list(REQUIRED_COST_COMPONENTS),
        "development_only": True,
        "not_oos_claim": True,
        "formal_walk_forward": False,
    }
