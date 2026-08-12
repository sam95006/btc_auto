"""Per-candidate sensitivity metrics — consume CostBridge outputs only."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.nexus_cost_sensitivity.constants import (
    CAPACITY_IMPACT_BPS_CAP,
    REQUIRED_OUTPUT_KEYS,
)
from backend.nexus_cost_sensitivity.cost_consumer import account_round_trip
from backend.nexus_cost_sensitivity.fixtures import SyntheticCandidate
from backend.nexus_cost_sensitivity.scenarios import (
    ScenarioPoint,
    baseline_params,
    iter_scenario_points,
)


def _d(x: float | int | str | Decimal) -> Decimal:
    return Decimal(str(x))


def _fmt(x: Decimal | float | int) -> str:
    return format(_d(x), "f")


def evaluate_point(candidate: SyntheticCandidate, point: ScenarioPoint) -> dict[str, Any]:
    p = point.params
    rt = account_round_trip(
        side=candidate.side,
        qty=candidate.qty,
        entry_price=candidate.entry_price,
        exit_price=candidate.exit_price,
        maker_taker_mix=float(p["maker_taker_mix"]),
        spread_bps=p["spread_bps"],
        slippage_bps=p["slippage_bps"],
        impact_bps=p["impact_bps"],
        funding_rate=p["funding_rate"],
        extra_fills=int(p["extra_fills"]),
        cancel_replace_cycles=int(p["cancel_replace_cycles"]),
        latency_ms=float(p["latency_ms"]),
        queue_position=float(p["queue_position"]),
        liquidity_collapse=float(p["liquidity_collapse"]),
        size_scale=float(p["size_scale"]),
    )
    n = max(1, int(candidate.sample_trade_count))
    gross = _d(rt["gross_pnl"]) * n
    net = _d(rt["net_pnl"]) * n
    total_cost = _d(rt["total_cost"]) * n
    return {
        "dimension": point.dimension,
        "scenario_label": point.label,
        "adverse": point.adverse,
        "per_trade": {
            "gross_pnl": _fmt(rt["gross_pnl"]),
            "net_pnl": _fmt(rt["net_pnl"]),
            "total_cost": _fmt(rt["total_cost"]),
            "cost_components": rt["cost_components"],
        },
        "scaled_trade_count": n,
        "gross_pnl": _fmt(gross),
        "net_pnl": _fmt(net),
        "total_cost": _fmt(total_cost),
        "cost_components": {
            k: _fmt(_d(v) * n) for k, v in rt["cost_components_decimal"].items()
        },
        "cost_bridge_verified": rt["cost_bridge_verified"],
        "market_impact_outside_cost_bridge": rt["market_impact_outside_cost_bridge"],
        "scenario_modifiers": rt["scenario_modifiers"],
        "cost_authority": rt["cost_authority"],
        "cost_model_version": rt["cost_model_version"],
        "_net_decimal": net,
        "_gross_decimal": gross,
        "_total_cost_decimal": total_cost,
        "_components_decimal": {
            k: _d(v) * n for k, v in rt["cost_components_decimal"].items()
        },
    }


def _maximum_viable_param(
    candidate: SyntheticCandidate,
    *,
    param_name: str,
    grid: list[Decimal],
) -> dict[str, Any]:
    """Largest grid value where scaled net expectancy stays strictly positive."""
    last_viable: Decimal | None = None
    for val in grid:
        params = baseline_params()
        params[param_name] = val
        point = ScenarioPoint(
            dimension=param_name,
            label=f"probe_{param_name}_{val}",
            adverse=False,
            params=params,
        )
        ev = evaluate_point(candidate, point)
        if ev["_net_decimal"] > 0:
            last_viable = val
        else:
            break
    return {
        "param": param_name,
        "maximum_viable": _fmt(last_viable) if last_viable is not None else "0",
        "viable": last_viable is not None,
        "grid": [_fmt(x) for x in grid],
    }


def capacity_estimate(candidate: SyntheticCandidate) -> dict[str, Any]:
    """Largest size_scale with net>0 and effective impact within CAPACITY_IMPACT_BPS_CAP."""
    scales = [Decimal(x) for x in ("0.5", "1", "1.5", "2", "3", "5", "8", "10", "15", "20")]
    last: Decimal | None = None
    last_detail: dict[str, Any] | None = None
    for scale in scales:
        params = baseline_params()
        params["size_scale"] = float(scale)
        point = ScenarioPoint(
            dimension="trade_size_scaling",
            label=f"capacity_{scale}",
            adverse=False,
            params=params,
        )
        ev = evaluate_point(candidate, point)
        impact_bps = _d(ev["scenario_modifiers"]["impact_bps"])
        if ev["_net_decimal"] > 0 and impact_bps <= _d(CAPACITY_IMPACT_BPS_CAP):
            last = scale
            last_detail = {
                "size_scale": _fmt(scale),
                "net_pnl": ev["net_pnl"],
                "impact_bps": _fmt(impact_bps),
            }
        else:
            break
    notional_1x = abs(candidate.qty * candidate.entry_price)
    capacity_notional = notional_1x * (last if last is not None else Decimal(0))
    return {
        "maximum_viable_size_scale": _fmt(last) if last is not None else "0",
        "capacity_notional_usdt": _fmt(capacity_notional),
        "impact_bps_cap": _fmt(CAPACITY_IMPACT_BPS_CAP),
        "last_viable_detail": last_detail,
        "capacity_limited": last is not None and last < Decimal("10"),
    }


def fragility_score(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    adverse = [e for e in evaluations if e.get("adverse")]
    if not adverse:
        return {
            "fragility_score": "0",
            "adverse_count": 0,
            "cost_destroyed_adverse_count": 0,
        }
    destroyed = sum(1 for e in adverse if e["_net_decimal"] <= 0)
    score = Decimal(destroyed) / Decimal(len(adverse))
    return {
        "fragility_score": _fmt(score),
        "adverse_count": len(adverse),
        "cost_destroyed_adverse_count": destroyed,
    }


def analyze_candidate(candidate: SyntheticCandidate) -> dict[str, Any]:
    baseline_point = ScenarioPoint(
        dimension="baseline",
        label="baseline_taker",
        adverse=False,
        params=baseline_params(),
    )
    baseline = evaluate_point(candidate, baseline_point)
    n = max(1, int(candidate.sample_trade_count))
    evaluations = [evaluate_point(candidate, p) for p in iter_scenario_points()]
    frag = fragility_score(evaluations)
    capacity = capacity_estimate(candidate)

    spread_probe = _maximum_viable_param(
        candidate,
        param_name="spread_bps",
        grid=[Decimal(x) for x in ("0.5", "1", "2", "3", "5", "8", "12", "20", "40", "80")],
    )
    slip_probe = _maximum_viable_param(
        candidate,
        param_name="slippage_bps",
        grid=[Decimal(x) for x in ("0.5", "1", "2", "3", "5", "8", "12", "20", "40", "80")],
    )

    gross_expectancy = baseline["_gross_decimal"] / Decimal(n)
    net_expectancy = baseline["_net_decimal"] / Decimal(n)
    # Break-even total cost equals gross PnL (net zero).
    break_even_cost = baseline["_gross_decimal"]

    dim_summaries: dict[str, Any] = {}
    for e in evaluations:
        dim = e["dimension"]
        bucket = dim_summaries.setdefault(
            dim,
            {"points": 0, "adverse_destroyed": 0, "adverse_total": 0, "min_net": None},
        )
        bucket["points"] += 1
        net_f = float(e["_net_decimal"])
        if bucket["min_net"] is None or net_f < float(bucket["min_net"]):
            bucket["min_net"] = e["net_pnl"]
        if e["adverse"]:
            bucket["adverse_total"] += 1
            if e["_net_decimal"] <= 0:
                bucket["adverse_destroyed"] += 1

    out = {
        "candidate_id": candidate.candidate_id,
        "mechanism_family": candidate.mechanism_family,
        "symbol": candidate.symbol,
        "sample_trade_count": candidate.sample_trade_count,
        "development_interval_id": candidate.development_interval_id,
        "oos_consumed": candidate.oos_consumed,
        "evidence_class": candidate.evidence_class,
        "gross_expectancy": _fmt(gross_expectancy),
        "cost_components": baseline["cost_components"],
        "net_expectancy": _fmt(net_expectancy),
        "break_even_cost": _fmt(break_even_cost),
        "maximum_viable_spread": spread_probe["maximum_viable"],
        "maximum_viable_slippage": slip_probe["maximum_viable"],
        "capacity_estimate": capacity,
        "fragility_score": frag["fragility_score"],
        "fragility_detail": frag,
        "spread_probe": spread_probe,
        "slippage_probe": slip_probe,
        "baseline": {
            "gross_pnl": baseline["gross_pnl"],
            "net_pnl": baseline["net_pnl"],
            "total_cost": baseline["total_cost"],
            "cost_components": baseline["cost_components"],
            "cost_authority": baseline["cost_authority"],
            "cost_model_version": baseline["cost_model_version"],
            "cost_bridge_verified": baseline["cost_bridge_verified"],
            "market_impact_outside_cost_bridge": baseline[
                "market_impact_outside_cost_bridge"
            ],
        },
        "dimension_summaries": dim_summaries,
        "scenario_count": len(evaluations),
        "scenario_evaluations": [
            {
                "dimension": e["dimension"],
                "scenario_label": e["scenario_label"],
                "adverse": e["adverse"],
                "gross_pnl": e["gross_pnl"],
                "net_pnl": e["net_pnl"],
                "total_cost": e["total_cost"],
            }
            for e in evaluations
        ],
        "_baseline_gross": baseline["_gross_decimal"],
        "_baseline_net": baseline["_net_decimal"],
        "_fragility": _d(frag["fragility_score"]),
        "_capacity_limited": bool(capacity.get("capacity_limited")),
    }
    missing = [k for k in REQUIRED_OUTPUT_KEYS if k not in out]
    if missing:
        raise AssertionError(f"missing_required_outputs={missing}")
    return out
