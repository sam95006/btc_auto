"""Historical execution-cost semantics — observed vs conservative proxy.

COMPATIBILITY SHIM: cost *formulas* and COST_MODEL_VERSION live in
``backend.nexus_execution.cost_model`` (canonical authority).

This module only annotates evidence source labels (OBSERVED vs PROXY) and
MUST re-export the canonical version string.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_execution.cost_model import (
    COST_MODEL_VERSION,
    get_cost_model_contract,
    migrate_cost_model_version,
)

ALLOWED_SOURCES = frozenset(
    {"OBSERVED", "POINT_IN_TIME_SNAPSHOT", "CONSERVATIVE_PROXY", "UNAVAILABLE"}
)

# Historical research label retained for artifact archaeology only.
RESEARCH_PROXY_LABEL_LEGACY = "NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1"
assert migrate_cost_model_version(RESEARCH_PROXY_LABEL_LEGACY) == COST_MODEL_VERSION


def annotate_trade_costs(
    row: dict[str, Any],
    *,
    spread_bps: float,
    slip_bps: float,
    funding_value: float | None = None,
    has_orderbook: bool = False,
) -> dict[str, Any]:
    """Label cost *sources* for research evidence — does not compute fee formulas."""
    spread_source = "OBSERVED" if has_orderbook else "CONSERVATIVE_PROXY"
    slip_source = "OBSERVED" if has_orderbook else "CONSERVATIVE_PROXY"
    if funding_value is None:
        funding_source = "UNAVAILABLE"
        funding_value = 0.0
    else:
        funding_source = "POINT_IN_TIME_SNAPSHOT"
    out = dict(row)
    out.update(
        {
            "spread_source": spread_source,
            "spread_value": float(spread_bps),
            "slippage_source": slip_source,
            "slippage_value": float(slip_bps),
            "funding_source": funding_source,
            "funding_value": float(funding_value),
            "cost_model_version": COST_MODEL_VERSION,
            "cost_model_authority": get_cost_model_contract().authority,
            "observed_execution_data": has_orderbook,
            "conservative_execution_proxy": not has_orderbook,
        }
    )
    assert out["spread_source"] in ALLOWED_SOURCES
    assert out["slippage_source"] in ALLOWED_SOURCES
    assert out["funding_source"] in ALLOWED_SOURCES
    return out


def cost_semantics_summary() -> dict[str, Any]:
    contract = get_cost_model_contract()
    return {
        "schema": "execution_cost_semantics_v1_1",
        "cost_model_version": COST_MODEL_VERSION,
        "cost_model_authority": contract.authority,
        "cost_model_schema": contract.schema,
        "observed_vs_proxy_separated": True,
        "configured_max_spread_is_not_observed_history": True,
        "allowed_sources": sorted(ALLOWED_SOURCES),
        "default_when_orderbook_unavailable": "CONSERVATIVE_PROXY",
        "formula_authority": "backend.nexus_execution.cost_model",
    }
