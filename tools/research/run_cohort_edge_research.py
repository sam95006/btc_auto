#!/usr/bin/env python3
"""Run strategy×regime×side cohort edge research. No trading session."""
from __future__ import annotations

import json
from pathlib import Path

from backend.nexus_demo_execution.cohort_edge_research import run_cohort_edge_research
from backend.nexus_demo_execution.historical_market_data import fetch_or_load_bundle, load_dataset

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "demo_validation_cohort_edge"
CACHE = ROOT / "artifacts" / "demo_validation_geometry_market_oos" / "market_cache"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    cache_files = sorted(CACHE.glob("*_15_*_*.json")) if CACHE.exists() else []
    by_sym: dict[str, Path] = {}
    for p in sorted(cache_files, key=lambda x: x.stat().st_size, reverse=True):
        sym = p.name.split("_")[0]
        if sym in symbols and sym not in by_sym:
            by_sym[sym] = p
    if len(by_sym) >= 3:
        datasets = [load_dataset(by_sym[s]) for s in symbols if s in by_sym]
    else:
        import time

        end_ms = int(time.time() * 1000)
        start_ms = end_ms - 180 * 24 * 60 * 60 * 1000
        datasets = fetch_or_load_bundle(
            symbols=symbols,
            interval="15",
            start_ms=start_ms,
            end_ms=end_ms,
            cache_dir=CACHE,
            use_network=True,
        )

    report = run_cohort_edge_research(datasets)
    (OUT / "cohort_edge_research_report.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    summary = {
        "recommendation": report.get("recommendation"),
        "cohorts_total": report.get("cohorts_total"),
        "cohorts_rejected": report.get("cohorts_rejected"),
        "cohorts_replay_validated": report.get("cohorts_replay_validated"),
        "cohorts_walk_forward_validated": report.get("cohorts_walk_forward_validated"),
        "cohorts_insufficient_sample": report.get("cohorts_insufficient_sample"),
        "range_struct_swing_status": report.get("range_struct_swing_status"),
        "no_gross_edge_cohort_count": report.get("no_gross_edge_cohort_count"),
        "cost_dominated_cohort_count": report.get("cost_dominated_cohort_count"),
        "edge_survives_base_cost_count": report.get("edge_survives_base_cost_count"),
        "edge_survives_adverse_cost_count": report.get("edge_survives_adverse_cost_count"),
        "new_untouched_oos_plan_ready": report.get("new_untouched_oos_plan_ready"),
        "top_by_net_exp": report.get("top_cohorts_by_net_expectancy"),
        "top_by_gross_exp": report.get("top_cohorts_by_gross_expectancy"),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
