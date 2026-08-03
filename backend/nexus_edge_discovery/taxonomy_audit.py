"""Independent diagnostic taxonomy for sealed V1.2 hypotheses — does not mutate V1.2."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_edge_discovery import DIAGNOSTIC_STATUSES


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def cost_bridge_from_sealed(hyp: dict[str, Any]) -> dict[str, Any]:
    """Derive execution-cost bridge from sealed aggregates (independent of discovery label)."""
    n = int(hyp.get("completed_trade_count") or 0)
    gross_pnl = _f(hyp.get("gross_pnl"))
    net_pnl = _f(hyp.get("net_pnl"))
    fees = _f(hyp.get("fees")) or 0.0
    slip = _f(hyp.get("slippage")) or 0.0
    funding = _f(hyp.get("funding")) or 0.0
    # Sealed rows do not always split entry/exit fee or spread; residual after fee+slip+funding is spread proxy
    residual = None
    if gross_pnl is not None and net_pnl is not None:
        total_cost = gross_pnl - net_pnl
        residual = total_cost - fees - slip - funding
        spread_cost = max(0.0, residual) if residual is not None else 0.0
    else:
        total_cost = fees + slip + funding
        spread_cost = 0.0
    # Conservative split of fees 50/50 when not instrumented
    entry_fee = fees * 0.5
    exit_fee = fees * 0.5
    g_exp = _f(hyp.get("gross_expectancy"))
    n_exp = _f(hyp.get("net_expectancy"))
    # profit_factor in V1.2 sealed package is net PF (misused as gross in discovery label path)
    net_pf = _f(hyp.get("profit_factor"))
    # Reconstruct gross PF only when we cannot — leave None unless estimable from expectancy signs
    gross_pf = None
    if g_exp is not None and g_exp > 0 and n > 0:
        # Cannot invent win/loss split; mark unavailable rather than reuse net PF
        gross_pf = None
    cost_per_trade = (total_cost / n) if n > 0 else None
    gross_edge_per_trade = g_exp
    net_edge_per_trade = n_exp
    ratio = None
    if g_exp is not None and g_exp > 0 and cost_per_trade is not None:
        ratio = cost_per_trade / g_exp
    return {
        "hypothesis_id": hyp.get("hypothesis_id"),
        "completed_trade_count": n,
        "gross_pnl": gross_pnl,
        "gross_expectancy": g_exp,
        "gross_profit_factor": gross_pf,
        "gross_profit_factor_note": "NOT_REUSED_FROM_NET_PF; win_loss_split_not_in_sealed_summary",
        "spread_cost": spread_cost,
        "slippage_cost": slip,
        "entry_fee_cost": entry_fee,
        "exit_fee_cost": exit_fee,
        "funding_cost": funding,
        "total_execution_cost": total_cost if gross_pnl is not None and net_pnl is not None else fees + slip + funding,
        "net_pnl": net_pnl,
        "net_expectancy": n_exp,
        "net_profit_factor": net_pf,
        "adverse_net_profit_factor": _f(hyp.get("adverse_profit_factor")),
        "cost_per_trade": cost_per_trade,
        "gross_edge_per_trade": gross_edge_per_trade,
        "net_edge_per_trade": net_edge_per_trade,
        "cost_to_gross_edge_ratio": ratio,
        "cost_bridge_identity": {
            "gross_minus_costs_equals_net": (
                abs((gross_pnl or 0) - (spread_cost + slip + fees + funding) - (net_pnl or 0)) < 1e-4
                if gross_pnl is not None and net_pnl is not None
                else None
            ),
            "residual_after_fee_slip_funding": residual,
        },
        "v1_2_development_status_preserved": hyp.get("development_status"),
        "v1_2_label_not_mutated": True,
    }


def classify_diagnostic(hyp: dict[str, Any], bridge: dict[str, Any]) -> str:
    funnel = hyp.get("candidate_funnel") or {}
    events = int(funnel.get("event_detected_count") or 0)
    trades = int(hyp.get("completed_trade_count") or 0)
    cost_blk = int(funnel.get("cost_gate_block_count") or 0)
    g_exp = bridge.get("gross_expectancy")
    n_exp = bridge.get("net_expectancy")
    fold_c = float(hyp.get("largest_fold_profit_contribution") or 0)
    sym_c = float(hyp.get("largest_symbol_profit_contribution") or 0)
    reg_c = float(hyp.get("largest_regime_profit_contribution") or 0)
    pos_folds = int(hyp.get("positive_development_fold_count") or 0)
    folds = int(hyp.get("development_fold_count") or 0)

    if events > 0 and trades == 0 and cost_blk >= events:
        return "EXECUTION_GATE_STARVED"
    if events > 0 and trades == 0 and cost_blk > 0 and cost_blk >= max(1, events // 2):
        return "EXECUTION_GATE_STARVED"
    if trades == 0 and events == 0:
        return "DATA_OR_METRIC_INVALID" if hyp.get("development_status") == "DISCOVERY_DATA_INVALID" else "RAW_SIGNAL_NO_EDGE"
    # Rare completed sample with positive gross: prefer insufficient-support over concentration
    if trades > 0 and trades < 30 and (g_exp is not None and g_exp > 0):
        return "RARE_EDGE_INSUFFICIENT_SUPPORT"
    if g_exp is not None and g_exp > 0 and n_exp is not None and n_exp <= 0:
        # Primary: cost destroyed. Concentration recorded as secondary in audit payload.
        return "RAW_EDGE_COST_DESTROYED"
    if g_exp is not None and g_exp <= 0:
        return "RAW_SIGNAL_NO_EDGE"
    if g_exp is not None and g_exp > 0 and n_exp is not None and n_exp > 0:
        if trades >= 50 and pos_folds >= 3 and folds >= 5 and sym_c <= 0.40 and reg_c <= 0.70 and fold_c <= 0.65:
            return "RAW_EDGE_DIAGNOSTIC_PROMISING"
        if trades < 50:
            return "RARE_EDGE_INSUFFICIENT_SUPPORT"
        if fold_c > 0.65 or sym_c > 0.40 or reg_c > 0.70:
            return (
                "RAW_EDGE_FOLD_CONCENTRATED"
                if fold_c > 0.65
                else ("RAW_EDGE_SYMBOL_CONCENTRATED" if sym_c > 0.40 else "RAW_EDGE_REGIME_CONCENTRATED")
            )
        if pos_folds < 2 and folds >= 5:
            return "RAW_EDGE_UNSTABLE"
        return "RAW_EDGE_UNSTABLE"
    if g_exp is None and n_exp is None and trades == 0:
        return "EXECUTION_GATE_STARVED" if events > 0 else "RAW_SIGNAL_NO_EDGE"
    return "DATA_OR_METRIC_INVALID"


def audit_v12_taxonomy(root: Path) -> dict[str, Any]:
    path = (
        root
        / "artifacts/readiness/immutable/strategy_engine_broad_coverage_v1_2/v1_2_development_research_summary.json"
    )
    sealed = json.loads(path.read_text(encoding="utf-8"))
    hyps = sealed.get("hypotheses") or []
    audits = []
    counts: dict[str, int] = {k: 0 for k in DIAGNOSTIC_STATUSES}
    for hyp in hyps:
        bridge = cost_bridge_from_sealed(hyp)
        diag = classify_diagnostic(hyp, bridge)
        assert diag in DIAGNOSTIC_STATUSES
        # Hard rule: positive gross + non-positive net cannot be NO_EDGE
        g = bridge.get("gross_expectancy")
        n = bridge.get("net_expectancy")
        if g is not None and g > 0 and n is not None and n <= 0:
            assert diag != "RAW_SIGNAL_NO_EDGE", hyp.get("hypothesis_id")
        counts[diag] = counts.get(diag, 0) + 1
        audits.append(
            {
                "hypothesis_id": hyp.get("hypothesis_id"),
                "component_executor_id": hyp.get("component_executor_id"),
                "v1_2_development_status": hyp.get("development_status"),
                "diagnostic_status": diag,
                "taxonomy_correction_required": (
                    hyp.get("development_status") == "DISCOVERY_NO_GROSS_EDGE" and diag == "RAW_EDGE_COST_DESTROYED"
                ),
                **bridge,
                "event_detected_count": (hyp.get("candidate_funnel") or {}).get("event_detected_count"),
                "cost_gate_block_count": (hyp.get("candidate_funnel") or {}).get("cost_gate_block_count"),
                "largest_fold_profit_contribution": hyp.get("largest_fold_profit_contribution"),
                "largest_symbol_profit_contribution": hyp.get("largest_symbol_profit_contribution"),
                "largest_regime_profit_contribution": hyp.get("largest_regime_profit_contribution"),
                "positive_development_fold_count": hyp.get("positive_development_fold_count"),
            }
        )
    h01 = next((a for a in audits if a["hypothesis_id"] == "V12_H01_TREND_CONTINUATION"), None)
    return {
        "schema": "v1_2_metric_taxonomy_audit",
        "package": "NEXUS_EDGE_DISCOVERY_DIAGNOSTICS_V2",
        "v1_2_package_mutated": False,
        "audited_hypothesis_count": len(audits),
        "counts": counts,
        "raw_signal_no_edge_count": counts.get("RAW_SIGNAL_NO_EDGE", 0),
        "raw_edge_cost_destroyed_count": counts.get("RAW_EDGE_COST_DESTROYED", 0),
        "raw_edge_unstable_count": counts.get("RAW_EDGE_UNSTABLE", 0),
        "raw_edge_concentrated_count": (
            counts.get("RAW_EDGE_FOLD_CONCENTRATED", 0)
            + counts.get("RAW_EDGE_SYMBOL_CONCENTRATED", 0)
            + counts.get("RAW_EDGE_REGIME_CONCENTRATED", 0)
        ),
        "rare_edge_insufficient_support_count": counts.get("RARE_EDGE_INSUFFICIENT_SUPPORT", 0),
        "execution_gate_starved_count": counts.get("EXECUTION_GATE_STARVED", 0),
        "raw_edge_diagnostic_promising_count": counts.get("RAW_EDGE_DIAGNOSTIC_PROMISING", 0),
        "audits": audits,
        "h01_explicit_audit": h01,
        "note": "V1.2 discovery labels preserved; diagnostic taxonomy is additive.",
    }
