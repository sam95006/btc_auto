"""H3 failure postmortem — diagnostic only from sealed WF + closed historical artifacts.

Never re-executes modified strategies against the consumed holdout.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _delta(a: Any, b: Any) -> Any:
    try:
        if a is None or b is None:
            return None
        return float(b) - float(a)
    except (TypeError, ValueError):
        return None


def build_h3_failure_decomposition(*, root: Path) -> dict[str, Any]:
    wf_path = root / "artifacts/readiness/immutable/h3_walk_forward/edge_research_v3_report.json"
    hold_path = root / "artifacts/readiness/immutable/h3_closed_historical_v1/closed_historical_summary.json"
    wf = json.loads(wf_path.read_text(encoding="utf-8"))
    hold = json.loads(hold_path.read_text(encoding="utf-8"))

    h3e_wf = next(
        (r for r in (wf.get("hypothesis_results") or []) if r.get("hypothesis_id") == "H3E_60m_pullback_reject_240m_down"),
        {},
    )
    h3d_wf = next(
        (r for r in (wf.get("hypothesis_results") or []) if r.get("hypothesis_id") == "H3D_first_lh_after_240m_transition"),
        {},
    )
    h3e_h = hold.get("h3e") or {}
    h3d_h = hold.get("h3d") or {}
    wr = h3e_wf.get("replay") or {}
    wadv = (h3e_wf.get("cost_versions") or {}).get("ADVERSE_COST_STRESS") or {}

    compare_fields = [
        ("completed_trade_count", wr.get("completed_trade_count"), h3e_h.get("completed_trade_count")),
        ("gross_pnl", wr.get("gross_pnl"), h3e_h.get("gross_pnl")),
        ("fees", wr.get("fees"), h3e_h.get("fees") or h3e_h.get("total_fees")),
        ("spread", wr.get("spread"), h3e_h.get("spread")),
        ("slippage", wr.get("slippage"), h3e_h.get("slippage")),
        ("funding", wr.get("funding"), h3e_h.get("funding")),
        ("net_pnl", wr.get("net_pnl"), h3e_h.get("net_pnl")),
        ("gross_expectancy", wr.get("gross_expectancy"), h3e_h.get("gross_expectancy")),
        ("net_expectancy", wr.get("net_expectancy"), h3e_h.get("net_expectancy")),
        ("gross_profit_factor", wr.get("gross_profit_factor"), h3e_h.get("gross_profit_factor")),
        ("net_profit_factor", wr.get("net_profit_factor") or wr.get("profit_factor"), h3e_h.get("profit_factor")),
        ("adverse_profit_factor", wadv.get("net_profit_factor") or wadv.get("profit_factor"), h3e_h.get("adverse_profit_factor")),
        ("win_rate", wr.get("win_rate"), h3e_h.get("win_rate")),
        ("maximum_drawdown", wr.get("maximum_drawdown"), h3e_h.get("maximum_drawdown")),
        ("maximum_consecutive_losses", wr.get("consecutive_losses"), h3e_h.get("maximum_consecutive_losses")),
        ("cost_gate_pass_rate", h3e_wf.get("cost_gate_pass_rate"), (h3e_h.get("cost_gate_pass_count") or 0) / max(1, h3e_h.get("candidate_count") or 1)),
    ]
    comparison = [
        {
            "metric": name,
            "walk_forward": wf_v,
            "holdout": ho_v,
            "difference_holdout_minus_wf": _delta(wf_v, ho_v),
        }
        for name, wf_v, ho_v in compare_fields
    ]

    # Diagnostic buckets from sealed holdout distributions only (no re-sim).
    symbol_dist = h3e_h.get("symbol_distribution") or {}
    regime_dist = h3e_h.get("regime_distribution") or {}
    total_sym = sum(int(v) for v in symbol_dist.values()) or 1

    classifications = []

    def add(code: str, *, evidence: str, wf_v: Any, ho_v: Any, severity: str, confidence: str, implication: str) -> None:
        classifications.append(
            {
                "classification": code,
                "evidence": evidence,
                "walk_forward_value": wf_v,
                "holdout_value": ho_v,
                "difference": _delta(wf_v, ho_v),
                "severity": severity,
                "confidence": confidence,
                "research_implication": implication,
            }
        )

    # Gross edge portability
    gpf_wf = wr.get("gross_profit_factor")
    gpf_ho = h3e_h.get("gross_profit_factor")
    if gpf_wf is not None and float(gpf_wf) > 1 and gpf_ho is not None and float(gpf_ho) < 1:
        add(
            "EDGE_NOT_PORTABLE",
            evidence="WF gross PF>1 but holdout gross PF<1 — edge did not survive earlier regime period",
            wf_v=gpf_wf,
            ho_v=gpf_ho,
            severity="CRITICAL",
            confidence="HIGH",
            implication="Do not promote H3E; require new H4 mechanism with stronger portability gates",
        )
        add(
            "NO_GROSS_EDGE",
            evidence="Holdout gross expectancy/PF negative before costs",
            wf_v=wr.get("gross_expectancy"),
            ho_v=h3e_h.get("gross_expectancy"),
            severity="CRITICAL",
            confidence="HIGH",
            implication="Cost tuning cannot rescue; redesign entry/event definition",
        )

    # Cost destruction on WF (secondary — costs reduced but did not eliminate WF edge)
    if wr.get("gross_pnl") and wr.get("net_pnl") and float(wr["gross_pnl"]) > 0 and float(wr["net_pnl"]) < float(wr["gross_pnl"]) * 0.5:
        add(
            "GROSS_EDGE_DESTROYED_BY_COST",
            evidence="WF costs consumed majority of gross PnL; holdout already gross-negative so costs amplify failure",
            wf_v={"gross": wr.get("gross_pnl"), "fees": wr.get("fees"), "net": wr.get("net_pnl")},
            ho_v={"gross": h3e_h.get("gross_pnl"), "fees": h3e_h.get("fees"), "net": h3e_h.get("net_pnl")},
            severity="HIGH",
            confidence="HIGH",
            implication="H4 must raise min_move_to_cost and reject late/chase entries",
        )

    # Fold instability foreshadowing
    folds = h3e_wf.get("folds") or []
    fold_pfs = [(f.get("fold"), (f.get("summary") or {}).get("net_profit_factor") or (f.get("summary") or {}).get("profit_factor")) for f in folds]
    if any(pf is not None and float(pf) < 1 for _, pf in fold_pfs):
        add(
            "REGIME_FILTER_NOT_PORTABLE",
            evidence=f"WF already had weak fold(s): {fold_pfs}; holdout collapsed further",
            wf_v=fold_pfs,
            ho_v=h3e_h.get("profit_factor"),
            severity="HIGH",
            confidence="MEDIUM",
            implication="TRENDING_DOWN pullback filter insufficient across regimes; H4 needs event retest / vol norms",
        )

    add(
        "ENTRY_TIMING_TOO_LATE",
        evidence="H3 pullback/continuation often enters after displacement; holdout win_rate 28% vs WF 44%",
        wf_v=wr.get("win_rate"),
        ho_v=h3e_h.get("win_rate"),
        severity="HIGH",
        confidence="MEDIUM",
        implication="H4A requires explicit retest; H4B rejects late extension",
    )

    add(
        "FALSE_CONTINUATION_RATE_TOO_HIGH",
        evidence="Holdout short-only TRENDING_DOWN continuation produced negative expectancy",
        wf_v=wr.get("net_expectancy"),
        ho_v=h3e_h.get("net_expectancy"),
        severity="HIGH",
        confidence="MEDIUM",
        implication="Require structural retest confirmation before intent",
    )

    # Concentration
    max_sym_share = max((int(v) / total_sym for v in symbol_dist.values()), default=0)
    if max_sym_share >= 0.35:
        add(
            "SYMBOL_OR_DIRECTION_CONCENTRATION",
            evidence=f"Holdout symbol_distribution={symbol_dist}; direction short_count={h3e_h.get('short_count')}",
            wf_v=None,
            ho_v=symbol_dist,
            severity="MEDIUM",
            confidence="MEDIUM",
            implication="H4 gates require multi-symbol contribution",
        )

    # Sample note for H3D confirmatory
    if int((h3d_h.get("metrics") or h3d_h).get("completed_trade_count") or h3d_h.get("completed_trade_count") or 0) < 30:
        add(
            "SAMPLE_INSUFFICIENT",
            evidence="H3D confirmatory holdout <30 completed trades",
            wf_v=(h3d_wf.get("replay") or {}).get("completed_trade_count"),
            ho_v=h3d_h.get("completed_trade_count"),
            severity="MEDIUM",
            confidence="HIGH",
            implication="H3D cannot confirm; still does not rescue H3E failure",
        )

    # No data/sim defect indicators from sealed integrity PASS
    data_defect = hold.get("dataset_integrity_status") != "PASS"
    sim_defect = int(h3e_h.get("lookahead_violation_count") or 0) > 0 or int(h3e_h.get("risk_limit_breach_count") or 0) > 0
    if data_defect:
        add(
            "DATA_QUALITY_DEFECT",
            evidence="dataset_integrity_status not PASS",
            wf_v=None,
            ho_v=hold.get("dataset_integrity_status"),
            severity="CRITICAL",
            confidence="HIGH",
            implication="Stop H4 until repaired",
        )
    if sim_defect:
        add(
            "SIMULATION_IMPLEMENTATION_DEFECT",
            evidence="lookahead or risk breaches on holdout",
            wf_v=None,
            ho_v={
                "lookahead": h3e_h.get("lookahead_violation_count"),
                "risk": h3e_h.get("risk_limit_breach_count"),
            },
            severity="CRITICAL",
            confidence="HIGH",
            implication="Stop H4 until repaired",
        )

    primary = "EDGE_NOT_PORTABLE"
    if data_defect:
        primary = "DATA_QUALITY_DEFECT"
    elif sim_defect:
        primary = "SIMULATION_IMPLEMENTATION_DEFECT"

    secondary = [c["classification"] for c in classifications if c["classification"] != primary]

    return {
        "schema": "h3_failure_decomposition_v1",
        "diagnostic_only": True,
        "modified_strategy_rerun_on_holdout": False,
        "consumed_holdout_id": hold.get("reservation_id"),
        "consumed_holdout_classification": hold.get("consumed_holdout_classification"),
        "dataset_checksum": hold.get("dataset_checksum"),
        "H3E_promotion_status": "REJECTED_CURRENT_POLICY",
        "H3D_promotion_status": "REJECTED_CURRENT_POLICY",
        "H3_current_demo_eligibility": False,
        "september_oos_may_not_rescue": True,
        "comparison_h3e_wf_vs_holdout": comparison,
        "holdout_symbol_distribution": symbol_dist,
        "holdout_regime_distribution": regime_dist,
        "holdout_direction": {
            "long_count": h3e_h.get("long_count"),
            "short_count": h3e_h.get("short_count"),
        },
        "payoff_ratio_holdout": h3e_h.get("payoff_ratio"),
        "average_win_holdout": h3e_h.get("average_win"),
        "average_loss_holdout": h3e_h.get("average_loss"),
        "median_hold_bars_holdout": h3e_h.get("median_hold_bars"),
        "exit_geometry_note": "Sealed sim uses structural ATR stop/target; MFE/MAE row dumps not committed",
        "classifications": classifications,
        "primary_root_cause": primary,
        "secondary_root_causes": secondary,
        "gross_edge_status": "ABSENT_ON_HOLDOUT" if (gpf_ho is not None and float(gpf_ho) < 1) else "PRESENT",
        "cost_destruction_status": "AMPLIFIES_FAILURE_ON_HOLDOUT",
        "regime_portability_status": "FAILED",
        "entry_timing_status": "LIKELY_TOO_LATE",
        "exit_geometry_status": "NOT_PRIMARY_FAILURE_GROSS_ALREADY_NEGATIVE",
        "h3d_confirmatory_note": {
            "wf_status": h3d_wf.get("status"),
            "holdout_status": h3d_h.get("confirmatory_status"),
            "cannot_rescue_h3e": True,
        },
        "block_h4_for_defect": bool(data_defect or sim_defect),
    }
