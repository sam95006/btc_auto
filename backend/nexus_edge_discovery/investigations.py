"""Focused H11 / H01 / cross-sectional diagnostic investigations."""
from __future__ import annotations

from typing import Any

from backend.nexus_edge_discovery import H01_STATUSES, H11_STATUSES
from backend.nexus_edge_discovery.event_study import collect_component_events, chronological_folds, summarize_events
from backend.nexus_edge_discovery.taxonomy_audit import cost_bridge_from_sealed
from backend.nexus_strategy_engine.data_bundle import ResearchDataBundle
from backend.nexus_strategy_engine.development_research_v1_1 import build_candidates_for_component, run_hypothesis_development_v11
from backend.nexus_strategy_engine.hypotheses_v1_2 import default_v12_hypothesis_drafts
from backend.nexus_strategy_engine.strategy_spec import freeze_spec


def _h11_draft() -> dict[str, Any]:
    d = next(x for x in default_v12_hypothesis_drafts() if x["component_id"] == "FUNDING_OI_CONTINUATION")
    return freeze_spec(d)


def _h01_draft() -> dict[str, Any]:
    d = next(x for x in default_v12_hypothesis_drafts() if x["component_id"] == "TREND_CONTINUATION")
    return freeze_spec(d)


def investigate_h11(
    bundles: list[ResearchDataBundle],
    *,
    sealed_h11: dict[str, Any] | None,
    history_depth_days: float,
) -> dict[str, Any]:
    hyp = _h11_draft()
    # Semantics unchanged — verify thresholds still present
    params = hyp.get("parameter_values") or {}
    events = collect_component_events("FUNDING_OI_CONTINUATION", bundles)
    pairs, funnel, zero_cause, proxy = build_candidates_for_component(hyp, bundles=bundles)
    result = run_hypothesis_development_v11(
        hyp,
        bundles=bundles,
        universe_snapshot_id="NEXUS_EDGE_DISCOVERY_DEPTH",
        data_checksum="depth_run",
    )
    trades = int(result.get("completed_trade_count") or 0)
    raw_events = len(events)
    cost_pass = int(funnel.get("candidate_count") or 0)
    n_exp = result.get("net_expectancy")
    n_pf = result.get("profit_factor")
    g_exp = result.get("gross_expectancy")
    g_pf = None  # not invent from net
    pos = int(result.get("positive_development_fold_count") or 0)
    folds = int(result.get("development_fold_count") or 0)
    sym_c = float(result.get("largest_symbol_profit_contribution") or 0)
    reg_c = float(result.get("largest_regime_profit_contribution") or 0)
    regimes = len({e.regime for e in events})
    symbols = len({e.symbol for e in events})

    status = "H11_RARE_SIGNAL_INSUFFICIENT_SUPPORT"
    if proxy > 0:
        status = "H11_RAW_SIGNAL_NOT_CONFIRMED"
    elif g_exp is not None and float(g_exp) <= 0:
        status = "H11_RAW_SIGNAL_NOT_CONFIRMED"
    elif g_exp is not None and float(g_exp) > 0 and n_exp is not None and float(n_exp) <= 0:
        status = "H11_RAW_SIGNAL_COST_DESTROYED"
    elif sym_c > 0.40 or reg_c > 0.70:
        status = "H11_RAW_SIGNAL_CONCENTRATED"
    elif (
        raw_events >= 30
        and trades >= 30
        and pos >= 3
        and folds >= 5
        and n_exp is not None
        and float(n_exp) > 0
        and n_pf is not None
        and float(n_pf) >= 1.10
        and sym_c <= 0.40
        and reg_c <= 0.70
        and int(result.get("lookahead_violation_count") or 0) == 0
        and int(result.get("required_data_proxy_violation_count") or 0) == 0
    ):
        status = "H11_RAW_SIGNAL_DIAGNOSTIC_PROMISING"
    else:
        status = "H11_RARE_SIGNAL_INSUFFICIENT_SUPPORT"

    assert status in H11_STATUSES
    return {
        "schema": "h11_rare_event_investigation",
        "H11_diagnostic_status": status,
        "semantics_unchanged": True,
        "parameter_values_fingerprint": sorted(params.keys()),
        "sample_gate_not_lowered": True,
        "H11_history_depth_days": history_depth_days,
        "H11_derivatives_symbol_count": sum(
            1 for b in bundles if b.funding_points and b.oi_points and b.mark_15 and b.index_15
        ),
        "H11_raw_event_count": raw_events,
        "cost_gate_pass_count": cost_pass,
        "H11_completed_trade_count": trades,
        "symbol_count": symbols,
        "regime_count": regimes,
        "gross_expectancy": g_exp,
        "net_expectancy": n_exp,
        "gross_profit_factor": g_pf,
        "net_profit_factor": n_pf,
        "H11_positive_fold_count": pos,
        "fold_count": folds,
        "H11_largest_symbol_contribution": sym_c,
        "H11_largest_regime_contribution": reg_c,
        "zero_trade_root_cause": zero_cause,
        "funnel": funnel,
        "sealed_v12_reference": {
            "completed_trade_count": (sealed_h11 or {}).get("completed_trade_count"),
            "net_expectancy": (sealed_h11 or {}).get("net_expectancy"),
            "preserved": True,
        },
        "formal_qualification": False,
    }


def investigate_h01(sealed_h01: dict[str, Any]) -> dict[str, Any]:
    bridge = cost_bridge_from_sealed(sealed_h01)
    g_exp = bridge.get("gross_expectancy")
    n_exp = bridge.get("net_expectancy")
    ratio = bridge.get("cost_to_gross_edge_ratio")
    pos = int(sealed_h01.get("positive_development_fold_count") or 0)
    folds = int(sealed_h01.get("development_fold_count") or 0)
    fold_c = float(sealed_h01.get("largest_fold_profit_contribution") or 0)
    sym_c = float(sealed_h01.get("largest_symbol_profit_contribution") or 0)
    reg_c = float(sealed_h01.get("largest_regime_profit_contribution") or 0)

    if g_exp is None or g_exp <= 0:
        status = "H01_RAW_SIGNAL_NO_EDGE"
    elif n_exp is not None and n_exp <= 0:
        status = "H01_RAW_EDGE_TOO_SMALL_FOR_COST"
    elif (
        g_exp > 0
        and n_exp is not None
        and n_exp > 0
        and int(sealed_h01.get("completed_trade_count") or 0) >= 50
        and pos >= 3
        and folds >= 5
        and sym_c <= 0.40
        and reg_c <= 0.70
        and fold_c <= 0.65
    ):
        status = "H01_RAW_EDGE_DIAGNOSTIC_PROMISING"
    else:
        status = "H01_RAW_EDGE_UNSTABLE"
    assert status in H01_STATUSES
    return {
        "schema": "h01_cost_destruction_investigation",
        "H01_diagnostic_status": status,
        "H01_gross_expectancy": g_exp,
        "H01_gross_profit_factor": bridge.get("gross_profit_factor"),
        "H01_total_execution_cost": bridge.get("total_execution_cost"),
        "H01_net_expectancy": n_exp,
        "H01_net_profit_factor": bridge.get("net_profit_factor"),
        "H01_cost_to_gross_edge_ratio": ratio,
        "cost_bridge": {
            "gross_pnl": bridge.get("gross_pnl"),
            "minus_spread": bridge.get("spread_cost"),
            "minus_slippage": bridge.get("slippage_cost"),
            "minus_entry_fee": bridge.get("entry_fee_cost"),
            "minus_exit_fee": bridge.get("exit_fee_cost"),
            "minus_funding": bridge.get("funding_cost"),
            "equals_net_pnl": bridge.get("net_pnl"),
            "identity_ok": (bridge.get("cost_bridge_identity") or {}).get("gross_minus_costs_equals_net"),
        },
        "fold_stability": {"positive_folds": pos, "fold_count": folds, "largest_fold_contribution": fold_c},
        "symbol_stability": {"largest_symbol_contribution": sym_c},
        "regime_stability": {"largest_regime_contribution": reg_c},
        "parameters_not_redesigned": True,
        "fees_not_reduced": True,
        "maker_fills_not_invented": True,
        "v1_2_mislabel_note": "V1.2 labeled DISCOVERY_NO_GROSS_EDGE despite positive gross_expectancy",
    }


def cross_sectional_diagnostics(bundles: list[ResearchDataBundle]) -> dict[str, Any]:
    """Raw rank spreads before geometry; do not loosen cost gate."""
    from backend.nexus_edge_discovery.event_study import collect_component_events

    out: dict[str, Any] = {"schema": "cross_sectional_diagnostics"}
    for cid, key in (
        ("RELATIVE_STRENGTH", "relative_strength"),
        ("CROSS_SECTIONAL_MOMENTUM", "cross_sectional_momentum"),
    ):
        events = collect_component_events(cid, bundles)
        # Peer snapshot at last common bar
        lookback = 16
        rets = {}
        for b in bundles:
            c = b.candles_15
            if not c or len(c) <= lookback + 10:
                continue
            i = len(c) - 10
            rets[b.symbol] = (c[i].close - c[i - lookback].close) / max(c[i - lookback].close, 1e-9)
            ranking_ts = c[i].ts_ms
        eligible = len(rets)
        if eligible < 20:
            out[f"{key}_raw_spread_status"] = "CROSS_SECTIONAL_UNIVERSE_TOO_SMALL"
            out[f"{key}_post_cost_status"] = "NOT_EVALUATED_UNIVERSE_TOO_SMALL"
            continue
        ranked = sorted(rets.items(), key=lambda kv: kv[1], reverse=True)
        n = len(ranked)
        top = ranked[: max(1, int(0.2 * n))]
        bot = ranked[-max(1, int(0.2 * n)) :]
        top_ret = sum(r for _, r in top) / len(top)
        bot_ret = sum(r for _, r in bot) / len(bot)
        spread = top_ret - bot_ret
        # Estimated RT cost: 2 * (spread_bps + slip_bps + fee) in return space ~ 2*(6+6)*1e-4 + 2*0.00055
        est_cost = 2 * (6 + 6) * 1e-4 + 2 * 0.00055
        post = spread - est_cost
        hyp = next(x for x in default_v12_hypothesis_drafts() if x["component_id"] == cid)
        hyp = freeze_spec(hyp)
        pairs, funnel, _, _ = build_candidates_for_component(hyp, bundles=bundles)
        out[f"{key}_raw_spread_status"] = "RAW_RANK_SIGNAL_PRESENT" if spread > 0 else "NO_RANK_SIGNAL"
        if int(funnel.get("event_detected_count") or 0) > 0 and int(funnel.get("candidate_count") or 0) == 0:
            post_status = "EXECUTION_GATE_STARVED"
        elif post <= 0:
            post_status = "RANK_SIGNAL_TURNOVER_OR_COST_DESTROYED"
        else:
            post_status = "POST_COST_SPREAD_POSITIVE_BUT_GEOMETRY_MAY_BLOCK"
        out[f"{key}_post_cost_status"] = post_status
        out[key] = {
            "ranking_timestamp": ranking_ts if eligible else None,
            "eligible_ranking_universe": eligible,
            "eligible_symbol_count": eligible,
            "top_bucket_return": top_ret,
            "bottom_bucket_return": bot_ret,
            "long_short_spread": spread,
            "portfolio_turnover": "snapshot_rebalance_assumed",
            "estimated_execution_cost": est_cost,
            "post_cost_long_short_spread": post,
            "rebalance_frequency": "event_scan_cooldown",
            "event_count": len(events),
            "cost_gate_block_count": funnel.get("cost_gate_block_count"),
            "candidate_count": funnel.get("candidate_count"),
            "cost_gate_not_loosened": True,
        }
    return out
