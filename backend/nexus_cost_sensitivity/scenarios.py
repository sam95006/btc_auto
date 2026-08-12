"""Deterministic sensitivity scenario grids (research modifiers only)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterator

from backend.nexus_cost_sensitivity.constants import SENSITIVITY_DIMENSIONS


@dataclass(frozen=True, slots=True)
class ScenarioPoint:
    dimension: str
    label: str
    adverse: bool
    params: dict[str, Any]


def baseline_params() -> dict[str, Any]:
    return {
        "maker_taker_mix": 1.0,
        "spread_bps": Decimal("1.0"),
        "slippage_bps": Decimal("2.0"),
        "impact_bps": Decimal("2.0"),
        "funding_rate": None,
        "extra_fills": 0,
        "cancel_replace_cycles": 0,
        "latency_ms": 0.0,
        "queue_position": 0.0,
        "liquidity_collapse": 1.0,
        "size_scale": 1.0,
    }


def _grid() -> dict[str, list[tuple[str, bool, dict[str, Any]]]]:
    """Per-dimension (point_label, adverse, param_overrides)."""
    return {
        "maker_taker_mix": [
            ("maker_maker", False, {"maker_taker_mix": 0.0}),
            ("maker_exit_taker", False, {"maker_taker_mix": 0.5}),
            ("taker_taker", True, {"maker_taker_mix": 1.0}),
        ],
        "spread": [
            ("spread_0p5bps", False, {"spread_bps": Decimal("0.5")}),
            ("spread_1bps", False, {"spread_bps": Decimal("1.0")}),
            ("spread_3bps", True, {"spread_bps": Decimal("3.0")}),
            ("spread_8bps", True, {"spread_bps": Decimal("8.0")}),
            ("spread_20bps", True, {"spread_bps": Decimal("20.0")}),
        ],
        "slippage": [
            ("slip_1bps", False, {"slippage_bps": Decimal("1.0")}),
            ("slip_2bps", False, {"slippage_bps": Decimal("2.0")}),
            ("slip_5bps", True, {"slippage_bps": Decimal("5.0")}),
            ("slip_12bps", True, {"slippage_bps": Decimal("12.0")}),
            ("slip_25bps", True, {"slippage_bps": Decimal("25.0")}),
        ],
        "market_impact": [
            ("impact_1bps", False, {"impact_bps": Decimal("1.0")}),
            ("impact_2bps", False, {"impact_bps": Decimal("2.0")}),
            ("impact_8bps", True, {"impact_bps": Decimal("8.0")}),
            ("impact_20bps", True, {"impact_bps": Decimal("20.0")}),
            ("impact_40bps", True, {"impact_bps": Decimal("40.0")}),
        ],
        "partial_fills": [
            ("fills_0", False, {"extra_fills": 0}),
            ("fills_1", False, {"extra_fills": 1}),
            ("fills_3", True, {"extra_fills": 3}),
            ("fills_8", True, {"extra_fills": 8}),
        ],
        "cancel_replace": [
            ("cr_0", False, {"cancel_replace_cycles": 0}),
            ("cr_1", False, {"cancel_replace_cycles": 1}),
            ("cr_4", True, {"cancel_replace_cycles": 4}),
            ("cr_10", True, {"cancel_replace_cycles": 10}),
        ],
        "funding": [
            ("funding_buffer", False, {"funding_rate": None}),
            ("funding_1bp", False, {"funding_rate": Decimal("0.0001")}),
            ("funding_5bp", True, {"funding_rate": Decimal("0.0005")}),
            ("funding_20bp", True, {"funding_rate": Decimal("0.002")}),
        ],
        "latency": [
            ("lat_0ms", False, {"latency_ms": 0.0}),
            ("lat_50ms", False, {"latency_ms": 50.0}),
            ("lat_200ms", True, {"latency_ms": 200.0}),
            ("lat_500ms", True, {"latency_ms": 500.0}),
            ("lat_1500ms", True, {"latency_ms": 1500.0}),
        ],
        "queue_position": [
            ("queue_front", False, {"queue_position": 0.0, "maker_taker_mix": 0.0}),
            ("queue_mid", False, {"queue_position": 0.4, "maker_taker_mix": 0.0}),
            ("queue_back", True, {"queue_position": 1.0, "maker_taker_mix": 0.0}),
        ],
        "liquidity_collapse": [
            ("liq_1x", False, {"liquidity_collapse": 1.0}),
            ("liq_1p5x", True, {"liquidity_collapse": 1.5}),
            ("liq_3x", True, {"liquidity_collapse": 3.0}),
            ("liq_6x", True, {"liquidity_collapse": 6.0}),
        ],
        "trade_size_scaling": [
            ("size_0p5x", False, {"size_scale": 0.5}),
            ("size_1x", False, {"size_scale": 1.0}),
            ("size_2x", True, {"size_scale": 2.0}),
            ("size_5x", True, {"size_scale": 5.0}),
            ("size_10x", True, {"size_scale": 10.0}),
        ],
    }


def iter_scenario_points() -> Iterator[ScenarioPoint]:
    grid = _grid()
    missing = [d for d in SENSITIVITY_DIMENSIONS if d not in grid]
    if missing:
        raise AssertionError(f"missing_sensitivity_dimensions={missing}")
    for dim in SENSITIVITY_DIMENSIONS:
        for label, adverse, overrides in grid[dim]:
            params = baseline_params()
            params.update(overrides)
            yield ScenarioPoint(
                dimension=dim,
                label=label,
                adverse=bool(adverse),
                params=params,
            )


def scenario_catalog() -> list[dict[str, Any]]:
    return [
        {
            "dimension": p.dimension,
            "label": p.label,
            "adverse": p.adverse,
            "param_keys": sorted(p.params.keys()),
        }
        for p in iter_scenario_points()
    ]


def assert_all_dimensions_covered() -> None:
    dims = {p.dimension for p in iter_scenario_points()}
    if dims != set(SENSITIVITY_DIMENSIONS):
        raise AssertionError(f"dimension_coverage_mismatch got={sorted(dims)}")
