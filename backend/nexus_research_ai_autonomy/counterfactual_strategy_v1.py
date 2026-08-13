"""Counterfactual strategy research on recorded OHLC shadow paths.

Does NOT change live STOP_PCT / TARGET_PCT / TRAIL_PCT.
Does NOT auto-promote any configuration.
Hot path: incremental/bounded batches only — never full history each cycle.
"""
from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
    RESEARCH_CONFIGS,
    commit_counterfactual_progress,
    evaluate_ohlc_path,
    path_records_for_counterfactual,
)
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import ledger_stats, shadow_dir


def _empty_acc() -> dict[str, Any]:
    return {
        "sample_count": 0,
        "wins": 0,
        "losses": 0,
        "sum_net": 0.0,
        "sum_gross": 0.0,
        "sum_cost": 0.0,
        "gw": 0.0,
        "gl": 0.0,
        "tbs": 0,
        "sbt": 0,
        "amb": 0,
        "unambiguous": 0,
    }


def _acc_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / "counterfactual_accumulator.json"


def _load_acc(campaign_root: Path) -> dict[str, Any]:
    path = _acc_path(campaign_root)
    if not path.exists():
        return {"schema": "v30_cf_accumulator_v1", "by_config": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {"by_config": {}}
    except Exception:  # noqa: BLE001
        return {"by_config": {}}


def _save_acc(campaign_root: Path, acc: dict[str, Any]) -> None:
    path = _acc_path(campaign_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    acc["updated_at_ms"] = int(time.time() * 1000)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(acc, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _update_acc(acc_row: dict[str, Any], m: dict[str, Any]) -> None:
    net = float(m.get("post_cost_hypothetical") or 0)
    gross = float(m.get("gross_hypothetical") or 0)
    cost = float(m.get("total_estimated_cost") or m.get("estimated_cost") or 0)
    acc_row["sample_count"] = int(acc_row.get("sample_count") or 0) + 1
    acc_row["sum_net"] = float(acc_row.get("sum_net") or 0) + net
    acc_row["sum_gross"] = float(acc_row.get("sum_gross") or 0) + gross
    acc_row["sum_cost"] = float(acc_row.get("sum_cost") or 0) + cost
    if net > 0:
        acc_row["wins"] = int(acc_row.get("wins") or 0) + 1
        acc_row["gw"] = float(acc_row.get("gw") or 0) + net
    elif net < 0:
        acc_row["losses"] = int(acc_row.get("losses") or 0) + 1
        acc_row["gl"] = float(acc_row.get("gl") or 0) + abs(net)
    if m.get("ambiguous_first_touch"):
        acc_row["amb"] = int(acc_row.get("amb") or 0) + 1
    else:
        acc_row["unambiguous"] = int(acc_row.get("unambiguous") or 0) + 1
        if m.get("target_before_stop") is True:
            acc_row["tbs"] = int(acc_row.get("tbs") or 0) + 1
        if m.get("stop_before_target") is True:
            acc_row["sbt"] = int(acc_row.get("sbt") or 0) + 1


def _stats_from_acc(a: dict[str, Any]) -> dict[str, Any]:
    n = int(a.get("sample_count") or 0)
    if n <= 0:
        return {
            "sample_count": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "post_cost_expectancy": None,
            "profit_factor": None,
            "gross_pnl": None,
            "estimated_cost": None,
            "net_pnl": None,
            "target_before_stop": 0,
            "stop_before_target": 0,
            "ambiguous_first_touch_count": 0,
        }
    wins = int(a.get("wins") or 0)
    gl = float(a.get("gl") or 0)
    unamb = int(a.get("unambiguous") or 0)
    tbs = int(a.get("tbs") or 0)
    sbt = int(a.get("sbt") or 0)
    amb = int(a.get("amb") or 0)
    return {
        "sample_count": n,
        "wins": wins,
        "losses": int(a.get("losses") or 0),
        "win_rate": round(wins / n, 4),
        "gross_pnl": round(float(a.get("sum_gross") or 0), 6),
        "estimated_cost": round(float(a.get("sum_cost") or 0), 6),
        "net_pnl": round(float(a.get("sum_net") or 0), 6),
        "post_cost_expectancy": round(float(a.get("sum_net") or 0) / n, 6),
        "profit_factor": round(float(a.get("gw") or 0) / gl, 4) if gl > 0 else None,
        "median_MFE": None,
        "median_MAE": None,
        "target_before_stop": tbs,
        "stop_before_target": sbt,
        "ambiguous_first_touch_count": amb,
        "target_before_stop_rate": round(tbs / unamb, 4) if unamb else None,
        "stop_before_target_rate": round(sbt / unamb, 4) if unamb else None,
        "ambiguous_rate": round(amb / n, 4),
        "incremental": True,
    }


def run_counterfactual_research(
    *,
    campaign_root: Path,
    path_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Incremental counterfactual on a bounded batch of new path records."""
    if path_records is None:
        path_records = path_records_for_counterfactual(campaign_root)

    acc = _load_acc(campaign_root)
    by_config = dict(acc.get("by_config") or {})
    batch_n = 0
    for cfg in RESEARCH_CONFIGS:
        name = cfg["name"]
        row = dict(by_config.get(name) or _empty_acc())
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
            _update_acc(row, m)
            batch_n += 1
        by_config[name] = row
    acc["by_config"] = by_config
    _save_acc(campaign_root, acc)
    commit_counterfactual_progress(campaign_root)

    config_results = []
    for cfg in RESEARCH_CONFIGS:
        stats = _stats_from_acc(by_config.get(cfg["name"]) or _empty_acc())
        if stats["sample_count"] == 0:
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
    led = ledger_stats(campaign_root)
    from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import ensure_path_index

    idx = ensure_path_index(campaign_root)
    report = {
        "schema": "v30_counterfactual_strategy_research_v1",
        "live_stop_pct_unchanged": True,
        "live_target_pct_unchanged": True,
        "live_trail_pct_unchanged": True,
        "auto_promotion": False,
        "mode": "incremental_bounded",
        "active_shadow_signals": led.get("unique_signal_ids"),
        "path_records_used": len(path_records),
        "batch_evaluations": batch_n,
        "recorded_path_records_on_disk": idx.get("path_record_rows"),
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
    """Per-horizon counts + MFE/MAE medians via streaming (bars discarded immediately)."""
    from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import (
        ensure_path_index,
        iter_jsonl_dicts,
        path_records_path,
    )

    idx = ensure_path_index(campaign_root)
    by_h: dict[str, dict[str, list[float]]] = {
        str(h): {"mfes": [], "maes": []} for h in (60, 180, 300, 900, 1800)
    }
    for rec in iter_jsonl_dicts(path_records_path(campaign_root)):
        try:
            h = int(rec.get("horizon_sec") or 0)
        except (TypeError, ValueError):
            continue
        key = str(h)
        if key not in by_h:
            continue
        # Never retain bars
        mfe = rec.get("MFE")
        mae = rec.get("MAE")
        if mfe is not None:
            try:
                by_h[key]["mfes"].append(float(mfe))
            except (TypeError, ValueError):
                pass
        if mae is not None:
            try:
                by_h[key]["maes"].append(float(mae))
            except (TypeError, ValueError):
                pass

    def _med(xs: list[float]) -> float | None:
        if not xs:
            return None
        s = sorted(xs)
        mid = len(s) // 2
        if len(s) % 2:
            return round(s[mid], 6)
        return round((s[mid - 1] + s[mid]) / 2.0, 6)

    vb = idx.get("valid_by_horizon") or {}
    label = {60: "1m", 180: "3m", 300: "5m", 900: "15m", 1800: "30m"}
    per_horizon = {}
    for h in (60, 180, 300, 900, 1800):
        hs = str(h)
        mfes = by_h[hs]["mfes"]
        maes = by_h[hs]["maes"]
        per_horizon[hs] = {
            "mature_sample_count": int(vb.get(label[h], 0)) or len(mfes),
            "median_MFE": _med(mfes),
            "median_MAE": _med(maes),
            "note": "streamed_scalars_bars_discarded",
        }
    return {
        "per_horizon": per_horizon,
        "lifecycle_counts": {},
        "decision_action_counts": {},
        "source": "shadow_path_index_plus_scalar_stream",
    }
