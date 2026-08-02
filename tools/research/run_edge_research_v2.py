#!/usr/bin/env python3
"""Edge Research V2 runner: audit, expand real data, nested WF. No trading."""
from __future__ import annotations

import json
import time
from pathlib import Path

from backend.nexus_demo_execution.edge_research_v2 import audit_datasets, run_edge_research_v2
from backend.nexus_demo_execution.historical_market_data import fetch_or_load_bundle, load_dataset

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "demo_validation_edge_research_v2"
OLD_CACHE = ROOT / "artifacts" / "demo_validation_geometry_market_oos" / "market_cache"
NEW_CACHE = OUT / "market_cache"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
# 540 calendar days — multi-regime coverage target
EXPAND_DAYS = 540


def _load_existing_15() -> list:
    files = sorted(OLD_CACHE.glob("*_15_1770111*.json")) if OLD_CACHE.exists() else []
    by: dict[str, Path] = {}
    for p in sorted(files, key=lambda x: x.stat().st_size, reverse=True):
        sym = p.name.split("_")[0]
        if sym in SYMBOLS and sym not in by:
            by[sym] = p
    return [load_dataset(by[s]) for s in SYMBOLS if s in by]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    NEW_CACHE.mkdir(parents=True, exist_ok=True)

    existing = _load_existing_15()
    existing_audit = audit_datasets(existing, stride=16)
    (OUT / "existing_dataset_audit.json").write_text(
        json.dumps(existing_audit, indent=2) + "\n", encoding="utf-8"
    )

    end_ms = max((d.end_time for d in existing), default=int(time.time() * 1000))
    start_ms = end_ms - EXPAND_DAYS * 24 * 60 * 60 * 1000

    print(
        json.dumps(
            {
                "expanding": True,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "days": EXPAND_DAYS,
                "existing_coverage": existing_audit.get("dataset_regime_coverage_status"),
            },
            indent=2,
        ),
        flush=True,
    )

    ds15 = fetch_or_load_bundle(
        symbols=SYMBOLS,
        interval="15",
        start_ms=start_ms,
        end_ms=end_ms,
        cache_dir=NEW_CACHE,
        use_network=True,
        max_pages=80,
    )
    ds60 = fetch_or_load_bundle(
        symbols=SYMBOLS,
        interval="60",
        start_ms=start_ms,
        end_ms=end_ms,
        cache_dir=NEW_CACHE,
        use_network=True,
        max_pages=40,
    )
    ds240 = fetch_or_load_bundle(
        symbols=SYMBOLS,
        interval="240",
        start_ms=start_ms,
        end_ms=end_ms,
        cache_dir=NEW_CACHE,
        use_network=True,
        max_pages=20,
    )

    expanded_audit = audit_datasets(ds15, stride=48)
    print("expanded_audit_done", expanded_audit.get("dataset_regime_coverage_status"), flush=True)
    report = run_edge_research_v2(
        datasets_15=ds15,
        datasets_60=ds60,
        datasets_240=ds240,
        existing_audit=existing_audit,
    )
    report["expanded_dataset_audit"] = expanded_audit
    (OUT / "edge_research_v2_report.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    summary = {
        "recommendation": report.get("recommendation"),
        "dataset_regime_coverage_status": existing_audit.get("dataset_regime_coverage_status"),
        "expanded_days": round((end_ms - start_ms) / 86_400_000.0, 1),
        "expanded_record_count": report.get("expanded_market_data", {}).get("record_count"),
        "breakout_sell": report.get("breakout_sell"),
        "vwap_range_sell": report.get("vwap_range_sell"),
        "trend_down_sell": report.get("trend_down_sell"),
        "cohorts_replay_validated": report.get("cohorts_replay_validated"),
        "cohorts_walk_forward_validated": report.get("cohorts_walk_forward_validated"),
        "cohorts_rejected": report.get("cohorts_rejected"),
        "cohorts_insufficient_sample": report.get("cohorts_insufficient_sample"),
        "primary_remaining_failure": report.get("primary_remaining_failure"),
        "new_untouched_oos_plan_ready": report.get("new_untouched_oos_plan_ready"),
        "oi_funding_cvd_data_plan_ready": report.get("oi_funding_cvd_data_plan_ready"),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
