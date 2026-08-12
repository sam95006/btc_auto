"""Counterfactual strategy research on recorded shadow paths.

Does NOT change live STOP_PCT / TARGET_PCT / TRAIL_PCT.
Does NOT auto-promote any configuration.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
    RESEARCH_CONFIGS,
    evaluate_path_mfe_mae,
)
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import shadow_dir


def _load_outcome_paths(campaign_root: Path) -> list[dict[str, Any]]:
    """Load recorded shadow outcomes that include enough fields for counterfactual."""
    path = shadow_dir(campaign_root) / "shadow_outcomes.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _load_signals(campaign_root: Path) -> list[dict[str, Any]]:
    path = shadow_dir(campaign_root) / "active_shadow_signals_latest.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return list(raw.get("signals") or [])
    except Exception:  # noqa: BLE001
        return []


def _aggregate_config_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "sample_count": 0,
            "win_rate": None,
            "post_cost_expectancy": None,
            "profit_factor": None,
            "median_MFE": None,
            "median_MAE": None,
            "fee_drag_total": None,
            "net_pnl": None,
            "gross_pnl": None,
        }
    nets = [float(r.get("post_cost_hypothetical") or 0) for r in results]
    grosses = [float(r.get("gross_hypothetical") or 0) for r in results]
    costs = [float(r.get("estimated_cost") or 0) for r in results]
    mfes = [float(r["MFE"]) for r in results if r.get("MFE") is not None]
    maes = [float(r["MAE"]) for r in results if r.get("MAE") is not None]
    wins = sum(1 for n in nets if n > 0)
    losses = sum(1 for n in nets if n < 0)
    gw = sum(n for n in nets if n > 0)
    gl = abs(sum(n for n in nets if n < 0))
    return {
        "sample_count": len(results),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(results), 4) if results else None,
        "post_cost_expectancy": round(sum(nets) / len(nets), 6),
        "profit_factor": round(gw / gl, 4) if gl > 0 else None,
        "median_MFE": round(statistics.median(mfes), 6) if mfes else None,
        "median_MAE": round(statistics.median(maes), 6) if maes else None,
        "fee_drag_total": round(sum(costs), 6),
        "net_pnl": round(sum(nets), 6),
        "gross_pnl": round(sum(grosses), 6),
        "trade_frequency_note": "derived_from_shadow_sample_only",
    }


def run_counterfactual_research(
    *,
    campaign_root: Path,
    path_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare champion vs alternative STOP/TARGET configs on recorded paths.

    path_records: optional list of {entry_price, direction, path: [(ts, px), ...]}
    If omitted, reports insufficient sample from outcomes file alone.
    """
    signals = _load_signals(campaign_root)
    outcomes = _load_outcome_paths(campaign_root)

    # Without full price paths we can only report champion outcome aggregates.
    champion_rows = [o for o in outcomes if o.get("post_cost_hypothetical") is not None]
    champion_stats = _aggregate_config_stats(
        [
            {
                "post_cost_hypothetical": o.get("post_cost_hypothetical"),
                "gross_hypothetical": o.get("gross_hypothetical")
                or (
                    float(o.get("post_cost_hypothetical") or 0)
                    + float(o.get("estimated_cost") or 0)
                ),
                "estimated_cost": o.get("estimated_cost") or 0,
                "MFE": o.get("MFE"),
                "MAE": o.get("MAE"),
            }
            for o in champion_rows
        ]
    )

    config_results: list[dict[str, Any]] = []
    if path_records:
        for cfg in RESEARCH_CONFIGS:
            rows = []
            for rec in path_records:
                m = evaluate_path_mfe_mae(
                    entry_price=float(rec["entry_price"]),
                    direction=str(rec.get("direction") or "LONG"),
                    path=list(rec.get("path") or []),
                    stop_pct=float(cfg["stop_pct"]),
                    target_pct=float(cfg["target_pct"]),
                    notional=float(rec.get("notional") or 350.0),
                )
                rows.append(m)
            stats = _aggregate_config_stats(rows)
            config_results.append(
                {
                    "config": cfg,
                    "stats": stats,
                    "auto_promoted": False,
                }
            )
    else:
        # Report configs as research candidates without fabricating path results
        for cfg in RESEARCH_CONFIGS:
            config_results.append(
                {
                    "config": cfg,
                    "stats": {
                        "sample_count": 0,
                        "status": "AWAITING_PATH_RECORDS",
                        "note": "provide path_records or accumulate shadow path dumps",
                    },
                    "auto_promoted": False,
                }
            )

    report = {
        "schema": "v30_counterfactual_strategy_research_v1",
        "live_stop_pct_unchanged": True,
        "live_target_pct_unchanged": True,
        "live_trail_pct_unchanged": True,
        "auto_promotion": False,
        "active_shadow_signals": len(signals),
        "recorded_outcomes": len(outcomes),
        "champion_v30_from_outcomes": champion_stats,
        "research_configs": config_results,
        "recommendation": "NO_AUTO_PROMOTION",
        "ready_for_demo_reenable": False,
    }

    out = shadow_dir(campaign_root) / "counterfactual_research_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(out)
    return report
