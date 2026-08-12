"""H3E/H3D closed historical holdout evaluation on frozen policies.

Historical simulation only. Does not write to Bybit Demo.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.edge_research_v3 import _simulate, build_v3_candidates
from backend.nexus_demo_execution.edge_research_v3_hypotheses import HYPOTHESES_V3
from backend.nexus_demo_execution.historical_market_data import Candle, MarketDataset
from backend.nexus_demo_execution.structural_geometry_qualify import evaluate_structural_geometry

# Frozen OOS qualification sample floor (market_event_sim.run_market_qualification).
MIN_SAMPLE_HOLDOUT = 30

H3E_ID = "H3E_60m_pullback_reject_240m_down"
H3D_ID = "H3D_first_lh_after_240m_transition"


def _hyp(hypothesis_id: str) -> dict[str, Any]:
    for h in HYPOTHESES_V3:
        if h["hypothesis_id"] == hypothesis_id:
            return h
    raise KeyError(hypothesis_id)


def _enrich_summary(base: dict[str, Any], rows: list[dict[str, Any]], *, gate_total: int, gate_pass: int) -> dict[str, Any]:
    filled = [r for r in rows if r.get("net_pnl") is not None]
    longs = sum(1 for r in filled if str(r.get("side") or "").lower() in {"buy", "long"})
    shorts = sum(1 for r in filled if str(r.get("side") or "").lower() in {"sell", "short"})
    holds = [int(r.get("holding_bars") or 0) for r in filled]
    wins = [float(r["net_pnl"]) for r in filled if float(r["net_pnl"]) > 0]
    losses = [float(r["net_pnl"]) for r in filled if float(r["net_pnl"]) <= 0]
    regimes: dict[str, int] = {}
    symbols: dict[str, int] = {}
    for r in filled:
        regimes[str(r.get("regime") or "UNKNOWN")] = regimes.get(str(r.get("regime") or "UNKNOWN"), 0) + 1
        symbols[str(r.get("symbol") or "?")] = symbols.get(str(r.get("symbol") or "?"), 0) + 1
    cons = 0
    max_cons = 0
    for r in filled:
        if float(r["net_pnl"]) <= 0:
            cons += 1
            max_cons = max(max_cons, cons)
        else:
            cons = 0
    entry_fees = sum(float(r.get("entry_fee") or 0) for r in filled)
    exit_fees = sum(float(r.get("exit_fee") or 0) for r in filled)
    total_fees = sum(float(r.get("total_fees") or r.get("fees") or 0) for r in filled)
    if total_fees == 0 and (entry_fees or exit_fees):
        total_fees = entry_fees + exit_fees
    out = dict(base)
    out.update(
        {
            "candidate_count": gate_total,
            "cost_gate_evaluated_count": gate_total,
            "cost_gate_pass_count": gate_pass,
            "cost_gate_block_count": max(0, gate_total - gate_pass),
            "entry_count": sum(1 for r in rows if r.get("entry_status") == "ENTRY_FILLED" or r.get("net_pnl") is not None),
            "completed_trade_count": int(base.get("completed_trade_count") or len(filled)),
            "symbol_distribution": symbols,
            "regime_distribution": regimes,
            "long_count": longs,
            "short_count": shorts,
            "entry_fees": round(entry_fees, 8) if filled else (0.0 if filled else None),
            "exit_fees": round(exit_fees, 8) if filled else (0.0 if filled else None),
            "total_fees": round(total_fees, 8) if filled else base.get("fees"),
            "average_win": (sum(wins) / len(wins)) if wins else None,
            "average_loss": (sum(losses) / len(losses)) if losses else None,
            "payoff_ratio": (
                (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
                if wins and losses and abs(sum(losses) / len(losses)) > 1e-12
                else None
            ),
            "maximum_consecutive_losses": max_cons if filled else 0,
            "median_hold_bars": (sorted(holds)[len(holds) // 2] if holds else None),
            "mean_hold_bars": (sum(holds) / len(holds) if holds else None),
            "liquidation_incident_count": int(base.get("liquidation_incident_count") or 0),
            "invalid_position_size_count": int(base.get("invalid_position_size_count") or 0),
            "risk_limit_breach_count": int(base.get("risk_limit_breach_count") or 0),
            "lookahead_violation_count": int(base.get("look_ahead_contamination") or 0),
            "data_quality_block_count": int(base.get("data_quality_block_count") or 0),
        }
    )
    # Alias fields required by Founder return
    if out.get("net_expectancy") is None and out.get("expectancy") is not None:
        out["net_expectancy"] = out["expectancy"]
    if out.get("gross_expectancy") is None and out.get("gross_pnl") is not None and filled:
        out["gross_expectancy"] = float(out["gross_pnl"]) / len(filled)
    return out


def evaluate_hypothesis_holdout(
    *,
    hypothesis_id: str,
    datasets_15: list[MarketDataset],
    datasets_60: list[MarketDataset],
    datasets_240: list[MarketDataset],
    micro: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hyp = _hyp(hypothesis_id)
    by60 = {d.symbol: d for d in datasets_60}
    by240 = {d.symbol: d for d in datasets_240}
    pairs: list[tuple[Any, list[Candle]]] = []
    gate_total = 0
    gate_pass = 0
    for ds in datasets_15:
        built = build_v3_candidates(
            hyp,
            ds15=ds,
            ds60=by60.get(ds.symbol),
            ds240=by240.get(ds.symbol),
            micro=micro or {},
            stride=16,
        )
        by_ts = {c.ts_ms: i for i, c in enumerate(ds.candles)}
        for cand, _meta in built:
            gate_total += 1
            geo = evaluate_structural_geometry(cand.evidence)
            if geo.get("cost_gate_pass"):
                gate_pass += 1
            idx = by_ts.get(cand.candidate_snapshot_time)
            if idx is None:
                continue
            pairs.append((cand, ds.candles[idx + 1 :]))
    pairs.sort(key=lambda x: x[0].candidate_snapshot_time)

    base_rows = _simulate(pairs, apply_costs=True, cost_mode="BASE_CONSERVATIVE")
    adv_rows = _simulate(pairs, apply_costs=True, cost_mode="ADVERSE_COST_STRESS")
    from backend.nexus_demo_execution.cohort_edge_research import _summ_rows

    base_s = _enrich_summary(_summ_rows(base_rows), base_rows, gate_total=gate_total, gate_pass=gate_pass)
    adv_s = _summ_rows(adv_rows)
    base_s["adverse_profit_factor"] = adv_s.get("net_profit_factor") or adv_s.get("profit_factor")
    base_s["adverse_net_pnl"] = adv_s.get("net_pnl")
    base_s["adverse_net_expectancy"] = adv_s.get("net_expectancy") or adv_s.get("expectancy")
    base_s["hypothesis_id"] = hypothesis_id
    return base_s


def classify_primary(summary: dict[str, Any], *, data_valid: bool) -> str:
    """Frozen OOS-style gates mapped to CLOSED_HISTORICAL_* statuses."""
    if not data_valid:
        return "CLOSED_HISTORICAL_DATA_INVALID"
    n = int(summary.get("completed_trade_count") or 0)
    required = (
        "net_pnl",
        "profit_factor",
        "net_expectancy",
        "maximum_drawdown",
        "win_rate",
        "gross_pnl",
    )
    if n == 0 or any(summary.get(k) is None for k in required):
        return "CLOSED_HISTORICAL_INSUFFICIENT_SAMPLE"
    if n < MIN_SAMPLE_HOLDOUT:
        return "CLOSED_HISTORICAL_INSUFFICIENT_SAMPLE"
    net = float(summary["net_pnl"])
    pf = float(summary.get("profit_factor") or summary.get("net_profit_factor") or 0)
    exp = float(summary["net_expectancy"])
    if not (net > 0 and pf > 1 and exp > 0):
        return "CLOSED_HISTORICAL_PERFORMANCE_FAILED"
    adv_pf = summary.get("adverse_profit_factor")
    adv_net = summary.get("adverse_net_pnl")
    if adv_pf is None or float(adv_pf) <= 1 or adv_net is None or float(adv_net) <= 0:
        return "CLOSED_HISTORICAL_PERFORMANCE_FAILED"
    return "CLOSED_HISTORICAL_PERFORMANCE_VALIDATED"


def classify_confirmatory(summary: dict[str, Any], *, data_valid: bool) -> str:
    if not data_valid:
        return "CONFIRMATORY_DATA_INVALID"
    n = int(summary.get("completed_trade_count") or 0)
    if n == 0 or summary.get("net_pnl") is None:
        return "CONFIRMATORY_INSUFFICIENT_SAMPLE"
    if n < MIN_SAMPLE_HOLDOUT:
        return "CONFIRMATORY_INSUFFICIENT_SAMPLE"
    net = float(summary["net_pnl"])
    pf = float(summary.get("profit_factor") or summary.get("net_profit_factor") or 0)
    exp = float(summary.get("net_expectancy") or summary.get("expectancy") or 0)
    if not (net > 0 and pf > 1 and exp > 0):
        return "CONFIRMATORY_FAILED"
    adv_pf = summary.get("adverse_profit_factor")
    adv_net = summary.get("adverse_net_pnl")
    if adv_pf is None or float(adv_pf) <= 1 or adv_net is None or float(adv_net) <= 0:
        return "CONFIRMATORY_FAILED"
    return "CONFIRMATORY_VALIDATED"


def recommendation_from_primary(primary_status: str) -> str:
    return {
        "CLOSED_HISTORICAL_PERFORMANCE_VALIDATED": "NEXUS_H3_CLOSED_HISTORICAL_VALIDATED_DEMO_FORWARD_APPROVAL_REQUIRED",
        "CLOSED_HISTORICAL_PERFORMANCE_FAILED": "NEXUS_H3_CLOSED_HISTORICAL_FAILED_RETURN_TO_RESEARCH",
        "CLOSED_HISTORICAL_INSUFFICIENT_SAMPLE": "NEXUS_H3_CLOSED_HISTORICAL_INSUFFICIENT_NEW_RESEARCH_REQUIRED",
        "CLOSED_HISTORICAL_DATA_INVALID": "NEXUS_H3_CLOSED_HISTORICAL_DATA_INVALID",
    }.get(primary_status, "NEXUS_H3_CLOSED_HISTORICAL_DATA_INVALID")
