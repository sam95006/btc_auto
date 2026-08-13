"""Compact internal shadow quality dashboard JSON — no UI."""
from __future__ import annotations

import json
import os
import statistics
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.counterfactual_strategy_v1 import (
    build_per_horizon_stats,
    run_counterfactual_research,
)
from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import load_path_records
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    load_shadow_signal_ledger,
    load_signal_state,
    shadow_dir,
)


def _git_commit() -> str | None:
    env = (os.environ.get("NEXUS_RUNTIME_COMMIT") or os.environ.get("GIT_COMMIT") or "").strip()
    if env:
        return env
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
        return out.strip() or None
    except Exception:  # noqa: BLE001
        return None


def build_shadow_quality_report(
    *,
    campaign_root: Path,
    counterfactual: dict[str, Any] | None = None,
) -> dict[str, Any]:
    signals = load_shadow_signal_ledger(campaign_root)
    state = load_signal_state(campaign_root)
    records = load_path_records(campaign_root)
    matured = [
        s
        for s in signals
        if (state.get("signals") or {}).get(str(s.get("signal_id") or ""), {}).get("fully_matured")
    ]
    horizon_pack = build_per_horizon_stats(campaign_root)
    cf = counterfactual or run_counterfactual_research(campaign_root=campaign_root)

    nets = [float(r.get("post_cost_hypothetical") or 0) for r in records]
    mfes = [float(r["MFE"]) for r in records if r.get("MFE") is not None]
    maes = [float(r["MAE"]) for r in records if r.get("MAE") is not None]
    costs = [float(r.get("total_estimated_cost") or r.get("estimated_cost") or 0) for r in records]
    amb = sum(1 for r in records if r.get("ambiguous_first_touch"))
    symbols = Counter(str(r.get("symbol") or "") for r in records)

    support: Counter[str] = Counter()
    contradict: Counter[str] = Counter()
    for s in signals:
        for e in s.get("supporting_evidence") or []:
            support[str(e)] += 1
        for e in s.get("contradicting_evidence") or []:
            contradict[str(e)] += 1

    warnings: list[str] = []
    for r in records:
        for w in r.get("data_quality_warnings") or []:
            warnings.append(str(w))
        if r.get("measurement_quality"):
            warnings.append(str(r["measurement_quality"]))
    warning_counts = dict(Counter(warnings).most_common(12))

    actions = horizon_pack.get("decision_action_counts") or {}
    gw = sum(n for n in nets if n > 0)
    gl = abs(sum(n for n in nets if n < 0))

    report = {
        "schema": "v30_shadow_quality_latest_v1",
        "runtime_commit": _git_commit(),
        "write_enabled": False,
        "signals_created": len(signals),
        "signals_matured": len(matured),
        "path_records": len(records),
        "per_horizon_stats": horizon_pack.get("per_horizon"),
        "READY_count": actions.get("READY", 0),
        "WATCH_count": actions.get("WATCH", 0),
        "WAIT_count": actions.get("WAIT", 0),
        "BLOCK_count": actions.get("BLOCK", 0),
        "post_cost_expectancy": round(sum(nets) / len(nets), 6) if nets else None,
        "profit_factor": round(gw / gl, 4) if gl > 0 else None,
        "median_MFE": round(statistics.median(mfes), 6) if mfes else None,
        "median_MAE": round(statistics.median(maes), 6) if maes else None,
        "cost_drag": round(sum(costs), 6) if costs else None,
        "ambiguous_first_touch_rate": round(amb / len(records), 4) if records else None,
        "symbol_concentration": dict(symbols.most_common(8)),
        "repeated_thesis_rate": None,  # filled when thesis rejections tracked in outcomes
        "top_supporting_evidence": support.most_common(8),
        "top_contradicting_evidence": contradict.most_common(8),
        "champion_vs_counterfactual_configs": cf.get("sample_counts") or {},
        "counterfactual_stats": {
            c["name"]: c["stats"] for c in (cf.get("research_configs") or [])
        },
        "data_quality_warnings": warning_counts,
        "path_source": "bybit_public_1m_ohlc",
        "close_only_MFE_removed": True,
        "ready_for_demo_reenable": False,
        "historical_similar_setup_stats": None,
    }

    out = shadow_dir(campaign_root) / "shadow_quality_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(out)
    return report
