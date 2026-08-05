"""Per-candidate deterministic risk/capacity metrics."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from backend.nexus_risk_capacity.constants import (
    CAPACITY_IMPACT_BPS_CAP,
    INSTRUMENT_CONCENTRATION_LIMIT,
    MAX_DRAWDOWN_ASSUMPTION_LIMIT,
    MIN_LIQUIDATION_DISTANCE_PCT,
    POSITION_CONCENTRATION_LIMIT,
    REGIME_CONCENTRATION_LIMIT,
    REQUIRED_OUTPUT_KEYS,
    STALE_DATA_MAX_AGE_SEC,
)
from backend.nexus_risk_capacity.cost_consumer import account_round_trip
from backend.nexus_risk_capacity.fixtures import SyntheticCandidate
from backend.nexus_risk_capacity.scenarios import (
    ScenarioPoint,
    baseline_params,
    iter_scenario_points,
)


def _d(x: float | int | str | Decimal) -> Decimal:
    return Decimal(str(x))


def _fmt(x: Decimal | float | int) -> str:
    return format(_d(x), "f")


_EXECUTION_DIMS = frozenset(
    {
        "fees",
        "spread",
        "slippage",
        "market_impact",
        "partial_fills",
        "cancel_replace",
        "funding",
        "latency",
        "queue_position",
        "liquidity_collapse",
        "trade_size_capacity",
    }
)


def evaluate_execution_point(
    candidate: SyntheticCandidate, point: ScenarioPoint
) -> dict[str, Any]:
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
        "kind": "execution",
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
        "passed": net > 0,
        "_net_decimal": net,
        "_gross_decimal": gross,
        "_total_cost_decimal": total_cost,
        "_components_decimal": {
            k: _d(v) * n for k, v in rt["cost_components_decimal"].items()
        },
    }


def evaluate_structural_point(
    candidate: SyntheticCandidate, point: ScenarioPoint
) -> dict[str, Any]:
    """Deterministic gates for concentration / drawdown / liquidation / data quality."""
    p = point.params
    dim = point.dimension
    detail: dict[str, Any] = {"dimension": dim, "scenario_label": point.label}

    if dim == "position_concentration":
        value = (
            _d(p["position_concentration_probe"])
            if p["position_concentration_probe"] is not None
            else candidate.position_concentration
        )
        limit = _d(POSITION_CONCENTRATION_LIMIT)
        passed = value <= limit
        detail.update({"value": _fmt(value), "limit": _fmt(limit)})
    elif dim == "instrument_concentration":
        value = (
            _d(p["instrument_concentration_probe"])
            if p["instrument_concentration_probe"] is not None
            else candidate.instrument_concentration
        )
        limit = _d(INSTRUMENT_CONCENTRATION_LIMIT)
        passed = value <= limit
        detail.update({"value": _fmt(value), "limit": _fmt(limit)})
    elif dim == "regime_concentration":
        value = (
            _d(p["regime_concentration_probe"])
            if p["regime_concentration_probe"] is not None
            else candidate.regime_concentration
        )
        limit = _d(REGIME_CONCENTRATION_LIMIT)
        passed = value <= limit
        detail.update({"value": _fmt(value), "limit": _fmt(limit)})
    elif dim == "max_drawdown_assumptions":
        value = (
            _d(p["assumed_max_drawdown_probe"])
            if p["assumed_max_drawdown_probe"] is not None
            else candidate.assumed_max_drawdown
        )
        limit = _d(MAX_DRAWDOWN_ASSUMPTION_LIMIT)
        passed = value <= limit
        detail.update({"value": _fmt(value), "limit": _fmt(limit)})
    elif dim == "liquidation_distance":
        value = (
            _d(p["liquidation_distance_probe"])
            if p["liquidation_distance_probe"] is not None
            else candidate.liquidation_distance_pct
        )
        limit = _d(MIN_LIQUIDATION_DISTANCE_PCT)
        passed = value >= limit
        detail.update({"value": _fmt(value), "min_distance_pct": _fmt(limit)})
    elif dim == "missing_data":
        missing = (
            bool(p["missing_data_probe"])
            if p["missing_data_probe"] is not None
            else candidate.missing_data
        )
        passed = not missing
        detail.update({"missing_data": missing})
    elif dim == "stale_data":
        stale_flag = (
            bool(p["stale_data_probe"])
            if p["stale_data_probe"] is not None
            else candidate.stale_data
        )
        age = (
            _d(p["data_age_sec_probe"])
            if p["data_age_sec_probe"] is not None
            else candidate.data_age_sec
        )
        age_stale = age > _d(STALE_DATA_MAX_AGE_SEC)
        passed = (not stale_flag) and (not age_stale)
        detail.update(
            {
                "stale_data": stale_flag,
                "data_age_sec": _fmt(age),
                "max_age_sec": _fmt(STALE_DATA_MAX_AGE_SEC),
                "age_stale": age_stale,
            }
        )
    else:
        raise AssertionError(f"unknown_structural_dimension={dim}")

    return {
        "dimension": dim,
        "scenario_label": point.label,
        "adverse": point.adverse,
        "kind": "structural",
        "passed": passed,
        "detail": detail,
        # Structural points do not produce PnL; keep zero for fragility math.
        "gross_pnl": "0",
        "net_pnl": "0" if passed else "-1",
        "_net_decimal": Decimal(0) if passed else Decimal("-1"),
        "_gross_decimal": Decimal(0),
    }


def evaluate_point(candidate: SyntheticCandidate, point: ScenarioPoint) -> dict[str, Any]:
    if point.dimension in _EXECUTION_DIMS:
        return evaluate_execution_point(candidate, point)
    return evaluate_structural_point(candidate, point)


def _maximum_viable_param(
    candidate: SyntheticCandidate,
    *,
    param_name: str,
    grid: list[Decimal],
) -> dict[str, Any]:
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
        ev = evaluate_execution_point(candidate, point)
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
    scales = [Decimal(x) for x in ("0.5", "1", "1.5", "2", "3", "5", "8", "10", "15", "20")]
    last: Decimal | None = None
    last_detail: dict[str, Any] | None = None
    for scale in scales:
        params = baseline_params()
        params["size_scale"] = float(scale)
        point = ScenarioPoint(
            dimension="trade_size_capacity",
            label=f"capacity_{scale}",
            adverse=False,
            params=params,
        )
        ev = evaluate_execution_point(candidate, point)
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
        return {"fragility_score": "0", "adverse_count": 0, "destroyed_count": 0}
    destroyed = 0
    for e in adverse:
        if e.get("kind") == "structural":
            if not e.get("passed"):
                destroyed += 1
        elif e["_net_decimal"] <= 0:
            destroyed += 1
    score = Decimal(destroyed) / Decimal(len(adverse))
    return {
        "fragility_score": _fmt(score),
        "adverse_count": len(adverse),
        "destroyed_count": destroyed,
        "_fragility": score,
    }


def concentration_review(candidate: SyntheticCandidate) -> dict[str, Any]:
    pos = candidate.position_concentration
    inst = candidate.instrument_concentration
    regime = candidate.regime_concentration
    blocked = (
        pos > _d(POSITION_CONCENTRATION_LIMIT)
        or inst > _d(INSTRUMENT_CONCENTRATION_LIMIT)
        or regime > _d(REGIME_CONCENTRATION_LIMIT)
    )
    return {
        "position_concentration": _fmt(pos),
        "instrument_concentration": _fmt(inst),
        "regime_concentration": _fmt(regime),
        "position_limit": _fmt(POSITION_CONCENTRATION_LIMIT),
        "instrument_limit": _fmt(INSTRUMENT_CONCENTRATION_LIMIT),
        "regime_limit": _fmt(REGIME_CONCENTRATION_LIMIT),
        "concentration_blocked": blocked,
    }


def drawdown_review(candidate: SyntheticCandidate) -> dict[str, Any]:
    mdd = candidate.assumed_max_drawdown
    unsafe = mdd > _d(MAX_DRAWDOWN_ASSUMPTION_LIMIT)
    return {
        "assumed_max_drawdown": _fmt(mdd),
        "limit": _fmt(MAX_DRAWDOWN_ASSUMPTION_LIMIT),
        "drawdown_assumption_unsafe": unsafe,
    }


def liquidation_distance_review(candidate: SyntheticCandidate) -> dict[str, Any]:
    dist = candidate.liquidation_distance_pct
    unsafe = dist < _d(MIN_LIQUIDATION_DISTANCE_PCT)
    return {
        "liquidation_distance_pct": _fmt(dist),
        "min_distance_pct": _fmt(MIN_LIQUIDATION_DISTANCE_PCT),
        "liquidation_distance_unsafe": unsafe,
    }


def data_quality_review(candidate: SyntheticCandidate) -> dict[str, Any]:
    age_stale = candidate.data_age_sec > _d(STALE_DATA_MAX_AGE_SEC)
    blocked = candidate.missing_data or candidate.stale_data or age_stale
    return {
        "missing_data": candidate.missing_data,
        "stale_data": candidate.stale_data,
        "data_age_sec": _fmt(candidate.data_age_sec),
        "max_age_sec": _fmt(STALE_DATA_MAX_AGE_SEC),
        "age_stale": age_stale,
        "data_quality_blocked": blocked,
    }


def deterministic_fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def analyze_candidate(candidate: SyntheticCandidate) -> dict[str, Any]:
    evaluations = [evaluate_point(candidate, p) for p in iter_scenario_points()]
    baseline_point = ScenarioPoint(
        dimension="fees",
        label="baseline",
        adverse=False,
        params=baseline_params(),
    )
    baseline = evaluate_execution_point(candidate, baseline_point)
    frag = fragility_score(evaluations)
    cap = capacity_estimate(candidate)
    spread_probe = _maximum_viable_param(
        candidate,
        param_name="spread_bps",
        grid=[Decimal(x) for x in ("0.5", "1", "2", "3", "5", "8", "12", "20", "40")],
    )
    slip_probe = _maximum_viable_param(
        candidate,
        param_name="slippage_bps",
        grid=[Decimal(x) for x in ("1", "2", "3", "5", "8", "12", "20", "30")],
    )

    conc = concentration_review(candidate)
    dd = drawdown_review(candidate)
    liq = liquidation_distance_review(candidate)
    dq = data_quality_review(candidate)

    dimension_summaries: dict[str, Any] = {}
    for e in evaluations:
        dim = e["dimension"]
        bucket = dimension_summaries.setdefault(
            dim, {"points": 0, "adverse_fail": 0, "pass": 0, "fail": 0}
        )
        bucket["points"] += 1
        passed = bool(e.get("passed"))
        if passed:
            bucket["pass"] += 1
        else:
            bucket["fail"] += 1
            if e.get("adverse"):
                bucket["adverse_fail"] += 1

    break_even = baseline["_total_cost_decimal"]
    result: dict[str, Any] = {
        "gross_expectancy": baseline["gross_pnl"],
        "net_expectancy": baseline["net_pnl"],
        "cost_components": baseline["cost_components"],
        "break_even_cost": _fmt(break_even),
        "maximum_viable_spread": spread_probe,
        "maximum_viable_slippage": slip_probe,
        "capacity_estimate": cap,
        "fragility_score": frag["fragility_score"],
        "fragility_detail": {
            "adverse_count": frag["adverse_count"],
            "destroyed_count": frag["destroyed_count"],
        },
        "concentration_review": conc,
        "drawdown_review": dd,
        "liquidation_distance_review": liq,
        "data_quality_review": dq,
        "baseline": {
            "gross_pnl": baseline["gross_pnl"],
            "net_pnl": baseline["net_pnl"],
            "total_cost": baseline["total_cost"],
            "cost_bridge_verified": baseline["cost_bridge_verified"],
            "market_impact_outside_cost_bridge": baseline[
                "market_impact_outside_cost_bridge"
            ],
            "cost_authority": baseline["cost_authority"],
            "cost_model_version": baseline["cost_model_version"],
        },
        "dimension_summaries": dimension_summaries,
        "scenario_count": len(evaluations),
        "scenario_evaluations": [
            {k: v for k, v in e.items() if not str(k).startswith("_")}
            for e in evaluations
        ],
        "spread_probe": spread_probe,
        "slippage_probe": slip_probe,
        "sample_trade_count": candidate.sample_trade_count,
        "data_quality_blocked": dq["data_quality_blocked"],
        "_baseline_gross": baseline["_gross_decimal"],
        "_baseline_net": baseline["_net_decimal"],
        "_fragility": frag["_fragility"],
        "_capacity_limited": cap["capacity_limited"],
        "_concentration_blocked": conc["concentration_blocked"],
        "_drawdown_unsafe": dd["drawdown_assumption_unsafe"],
        "_liquidation_unsafe": liq["liquidation_distance_unsafe"],
    }
    # Fingerprint excludes internal decimal helpers and full scenario dump size noise:
    # hash the stable required outputs.
    fp_payload = {
        k: result[k]
        for k in REQUIRED_OUTPUT_KEYS
        if k
        not in {
            "deterministic_fingerprint",
            "ai_override_attempted",
            "ai_override_applied",
        }
        and k in result
    }
    fp_payload["candidate_id"] = candidate.candidate_id
    result["deterministic_fingerprint"] = deterministic_fingerprint(fp_payload)
    result["ai_override_attempted"] = False
    result["ai_override_applied"] = False
    return result
