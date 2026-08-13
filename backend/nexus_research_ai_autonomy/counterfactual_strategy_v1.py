"""Counterfactual strategy research on recorded OHLC shadow paths.

Does NOT change live STOP_PCT / TARGET_PCT / TRAIL_PCT.
Does NOT auto-promote any configuration.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
    RESEARCH_CONFIGS,
    evaluate_ohlc_path,
    load_path_records,
    path_records_for_counterfactual,
)
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import load_shadow_signal_ledger, shadow_dir


def _load_signals(campaign_root: Path) -> list[dict[str, Any]]:
    return load_shadow_signal_ledger(campaign_root)


def _aggregate_config_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "sample_count": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "gross_pnl": None,
            "estimated_cost": None,
            "net_pnl": None,
            "post_cost_expectancy": None,
            "profit_factor": None,
            "median_MFE": None,
            "median_MAE": None,
            "target_before_stop": 0,
            "stop_before_target": 0,
            "ambiguous_first_touch_count": 0,
        }
    nets = [float(r.get("post_cost_hypothetical") or 0) for r in results]
    grosses = [float(r.get("gross_hypothetical") or 0) for r in results]
    costs = [float(r.get("total_estimated_cost") or r.get("estimated_cost") or 0) for r in results]
    mfes = [float(r["MFE"]) for r in results if r.get("MFE") is not None]
    maes = [float(r["MAE"]) for r in results if r.get("MAE") is not None]
    wins = sum(1 for n in nets if n > 0)
    losses = sum(1 for n in nets if n < 0)
    gw = sum(n for n in nets if n > 0)
    gl = abs(sum(n for n in nets if n < 0))
    # Exclude ambiguous from first-touch rates
    unambiguous = [r for r in results if not r.get("ambiguous_first_touch")]
    tbs = sum(1 for r in unambiguous if r.get("target_before_stop") is True)
    sbt = sum(1 for r in unambiguous if r.get("stop_before_target") is True)
    amb = sum(1 for r in results if r.get("ambiguous_first_touch"))
    return {
        "sample_count": len(results),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(results), 4) if results else None,
        "gross_pnl": round(sum(grosses), 6),
        "estimated_cost": round(sum(costs), 6),
        "net_pnl": round(sum(nets), 6),
        "post_cost_expectancy": round(sum(nets) / len(nets), 6),
        "profit_factor": round(gw / gl, 4) if gl > 0 else None,
        "median_MFE": round(statistics.median(mfes), 6) if mfes else None,
        "median_MAE": round(statistics.median(maes), 6) if maes else None,
        "target_before_stop": tbs,
        "stop_before_target": sbt,
        "ambiguous_first_touch_count": amb,
        "target_before_stop_rate": round(tbs / len(unambiguous), 4) if unambiguous else None,
        "stop_before_target_rate": round(sbt / len(unambiguous), 4) if unambiguous else None,
        "ambiguous_rate": round(amb / len(results), 4) if results else None,
    }


def run_counterfactual_research(
    *,
    campaign_root: Path,
    path_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare champion vs alternative STOP/TARGET configs on OHLC path records."""
    signals = _load_signals(campaign_root)
    if path_records is None:
        path_records = path_records_for_counterfactual(campaign_root)

    config_results: list[dict[str, Any]] = []
    for cfg in RESEARCH_CONFIGS:
        rows: list[dict[str, Any]] = []
        for rec in path_records:
            bars = list(rec.get("bars") or [])
            if not bars:
                continue
            m = evaluate_ohlc_path(
                entry_price=float(rec["entry_price"]),
                direction=str(rec.get("direction") or "LONG"),
                bars=bars,
                stop_pct=float(cfg["stop_pct"]),
                target_pct=float(cfg["target_pct"]),
                notional=float(rec.get("notional") or 350.0),
            )
            rows.append(m)
        stats = _aggregate_config_stats(rows)
        if not path_records:
            stats["status"] = "AWAITING_PATH_RECORDS"
        config_results.append(
            {
                "config": cfg,
                "name": cfg["name"],
                "stats": stats,
                "auto_promoted": False,
            }
        )

    by_name = {c["name"]: c["stats"] for c in config_results}
    report = {
        "schema": "v30_counterfactual_strategy_research_v1",
        "live_stop_pct_unchanged": True,
        "live_target_pct_unchanged": True,
        "live_trail_pct_unchanged": True,
        "auto_promotion": False,
        "active_shadow_signals": len(signals),
        "path_records_used": len(path_records),
        "recorded_path_records_on_disk": len(load_path_records(campaign_root)),
        "champion_v30": by_name.get("champion_v30"),
        "research_configs": config_results,
        "sample_counts": {c["name"]: c["stats"].get("sample_count", 0) for c in config_results},
        "recommendation": "NO_AUTO_PROMOTION",
        "ready_for_demo_reenable": False,
    }

    out = shadow_dir(campaign_root) / "counterfactual_research_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(out)
    return report


def build_per_horizon_stats(campaign_root: Path) -> dict[str, Any]:
    """Independent stats per horizon — never mix into one win-rate."""
    records = load_path_records(campaign_root)
    signals = _load_signals(campaign_root)
    action_counts = Counter(str(s.get("lifecycle_state") or "UNKNOWN") for s in signals)
    # Also count from latest snapshots if available
    from backend.nexus_research_ai_autonomy.decision_snapshot_v30 import load_latest_snapshots

    snaps = load_latest_snapshots(campaign_root)
    action_from_snap = Counter(str(s.get("final_action") or "WAIT") for s in snaps)

    by_h: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        h = str(r.get("horizon_sec") or "unknown")
        by_h.setdefault(h, []).append(r)

    per_horizon: dict[str, Any] = {}
    for h, rows in sorted(by_h.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        stats = _aggregate_config_stats(rows)
        symbols = Counter(str(r.get("symbol") or "") for r in rows)
        top_sym = symbols.most_common(1)
        conc = (top_sym[0][1] / len(rows)) if rows and top_sym else None
        costs = [float(r.get("total_estimated_cost") or r.get("estimated_cost") or 0) for r in rows]
        grosses = [float(r.get("gross_hypothetical") or 0) for r in rows]
        edge_ratios = []
        for g, c in zip(grosses, costs):
            if c > 0:
                edge_ratios.append(abs(g) / c)
        per_horizon[h] = {
            "mature_sample_count": len(rows),
            **stats,
            "gross_expectancy": round(sum(grosses) / len(grosses), 6) if grosses else None,
            "cost": round(sum(costs), 6),
            "edge_to_cost_ratio_median": (
                round(statistics.median(edge_ratios), 4) if edge_ratios else None
            ),
            "symbol_concentration": dict(symbols.most_common(5)),
            "top_symbol_share": round(conc, 4) if conc is not None else None,
        }

    return {
        "per_horizon": per_horizon,
        "lifecycle_counts": dict(action_counts),
        "decision_action_counts": {
            "READY": action_from_snap.get("SELECT", 0),
            "WATCH": action_from_snap.get("WATCH", 0),
            "WAIT": action_from_snap.get("WAIT", 0),
            "BLOCK": action_from_snap.get("BLOCK", 0),
        },
    }
