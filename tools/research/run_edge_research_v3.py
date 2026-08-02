#!/usr/bin/env python3
"""Edge Research V3 runner — economic redesign. No trading / no final OOS."""
from __future__ import annotations

import json
from pathlib import Path

from backend.nexus_demo_execution.edge_research_v3 import (
    cost_gate_starvation_forensic,
    run_edge_research_v3,
)
from backend.nexus_demo_execution.historical_market_data import load_dataset
from backend.nexus_demo_execution.microstructure_history import fetch_or_load_micro_bundle

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "demo_validation_edge_research_v3"
KLINE_CACHE = ROOT / "artifacts" / "demo_validation_edge_research_v2" / "market_cache"
MICRO_CACHE = OUT / "micro_cache"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]


def _load_interval(interval: str) -> list:
    files = sorted(KLINE_CACHE.glob(f"*_{interval}_1739007*.json"))
    by: dict[str, Path] = {}
    for p in files:
        sym = p.name.split("_")[0]
        if sym in SYMBOLS and sym not in by:
            by[sym] = p
    return [load_dataset(by[s]) for s in SYMBOLS if s in by]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    MICRO_CACHE.mkdir(parents=True, exist_ok=True)
    ds15 = _load_interval("15")
    ds60 = _load_interval("60")
    ds240 = _load_interval("240")
    assert ds15 and ds60 and ds240, "expanded V2 market cache required"
    start_ms = min(d.start_time for d in ds15)
    end_ms = max(d.end_time for d in ds15)
    print(json.dumps({"loading_micro": True, "start_ms": start_ms, "end_ms": end_ms}, indent=2), flush=True)
    micro = fetch_or_load_micro_bundle(
        symbols=SYMBOLS, start_ms=start_ms, end_ms=end_ms, cache_dir=MICRO_CACHE, use_network=True
    )
    print("starvation_forensic...", flush=True)
    starvation = cost_gate_starvation_forensic(ds15, ds60, stride=32)
    (OUT / "cost_gate_starvation_forensic.json").write_text(
        json.dumps(starvation, indent=2, default=str) + "\n", encoding="utf-8"
    )
    report = run_edge_research_v3(
        datasets_15=ds15,
        datasets_60=ds60,
        datasets_240=ds240,
        micro=micro,
        starvation=starvation,
    )
    (OUT / "edge_research_v3_report.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    summary = {
        "recommendation": report.get("recommendation"),
        "cost_gate_starvation_counts_by_cause": report.get("cost_gate_starvation_counts_by_cause"),
        "oi_data_status": report.get("oi_data_status"),
        "funding_data_status": report.get("funding_data_status"),
        "trade_flow_data_status": report.get("trade_flow_data_status"),
        "cvd_data_status": report.get("cvd_data_status"),
        "h1_best": report.get("h1_best"),
        "h2_best": report.get("h2_best"),
        "h3_best": report.get("h3_best"),
        "cohorts_replay_validated": report.get("cohorts_replay_validated"),
        "cohorts_walk_forward_validated": report.get("cohorts_walk_forward_validated"),
        "cohorts_rejected": report.get("cohorts_rejected"),
        "cohorts_insufficient_sample": report.get("cohorts_insufficient_sample"),
        "primary_remaining_failure": report.get("primary_remaining_failure"),
        "new_untouched_oos_plan_ready": report.get("new_untouched_oos_plan_ready"),
    }
    print(json.dumps(summary, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
