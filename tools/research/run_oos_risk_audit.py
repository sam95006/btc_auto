#!/usr/bin/env python3
"""Run OOS risk-model audit + recalculated attribution. No trading session."""
from __future__ import annotations

import json
from pathlib import Path

from backend.nexus_demo_execution.historical_market_data import fetch_or_load_bundle
from backend.nexus_demo_execution.oos_risk_audit import CONSUMED_OOS_ID, CONSUMED_STATUS, run_recalculated_pipeline

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "demo_validation_geometry_market_oos"
CACHE = OUT / "market_cache"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # Reuse cached 180d datasets if present; else fetch.
    cache_files = sorted(CACHE.glob("*_15_*_*.json"))
    # Prefer longest window caches (180d) — filenames embed start/end
    long_caches = [p for p in cache_files if "1770111" in p.name or (p.stat().st_size > 2_000_000)]
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    if len(long_caches) >= 3:
        from backend.nexus_demo_execution.historical_market_data import load_dataset

        # one file per symbol (largest)
        by_sym: dict[str, Path] = {}
        for p in sorted(cache_files, key=lambda x: x.stat().st_size, reverse=True):
            sym = p.name.split("_")[0]
            if sym in symbols and sym not in by_sym:
                by_sym[sym] = p
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

    report = run_recalculated_pipeline(datasets, min_sample=30)
    consumed = {
        "oos_cohort_id": CONSUMED_OOS_ID,
        "oos_cohort_status": CONSUMED_STATUS,
        "qualification_commit_ref": "e186d130552e2456d9c26df2feb0ac8667dee54f",
        "reuse_forbidden": True,
        "requires_new_untouched_oos": True,
    }
    (OUT / "consumed_oos_holdout.json").write_text(json.dumps(consumed, indent=2) + "\n", encoding="utf-8")
    (OUT / "risk_model_audit_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "simulator_risk_model_result": report.get("simulator_risk_model_result"),
                "recommendation": report.get("recommendation"),
                "gross_edge_classification": report.get("gross_edge_classification"),
                "primary_failure_classification": report.get("primary_failure_classification"),
                "recalculated_wf_trades": (report.get("recalculated_wf") or {}).get("simulated_trade_count"),
                "recalculated_wf_net_pnl": (report.get("recalculated_wf") or {}).get("net_pnl"),
                "recalculated_oos_status": report.get("recalculated_oos_status"),
                "recalculated_oos_trades": (report.get("recalculated_oos_diagnostic_on_consumed_holdout") or {}).get(
                    "simulated_trade_count"
                ),
                "risk_budget_breach_count": report.get("risk_budget_breach_count"),
                "invalid_position_size_trade_count": report.get("invalid_position_size_trade_count"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
