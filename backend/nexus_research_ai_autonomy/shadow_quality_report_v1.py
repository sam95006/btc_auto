"""Compact internal shadow quality dashboard JSON — no UI.

Hot cycle: lightweight from index + prior counterfactual — no full OHLC reload.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.counterfactual_strategy_v1 import build_per_horizon_stats
from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import ensure_path_index, rss_mb
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    ledger_stats,
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


def _should_run_heavy(campaign_root: Path) -> bool:
    """Throttle heavy quality refresh (default every 15 minutes)."""
    try:
        every = int(os.environ.get("NEXUS_SHADOW_QUALITY_EVERY_SEC") or 900)
    except (TypeError, ValueError):
        every = 900
    marker = shadow_dir(campaign_root) / "shadow_quality_latest.json"
    if not marker.exists():
        return True
    age = time.time() - marker.stat().st_mtime
    return age >= every


def build_shadow_quality_report(
    *,
    campaign_root: Path,
    counterfactual: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    led = ledger_stats(campaign_root)
    state = load_signal_state(campaign_root)
    idx = ensure_path_index(campaign_root)
    run_heavy = force or _should_run_heavy(campaign_root)
    if run_heavy:
        horizon_pack = build_per_horizon_stats(campaign_root)
    else:
        vb = idx.get("valid_by_horizon") or {}
        horizon_pack = {
            "per_horizon": {
                str(h): {
                    "mature_sample_count": int(vb.get(lab, 0) or 0),
                    "median_MFE": None,
                    "median_MAE": None,
                    "note": "deferred_use_index_counts_only",
                }
                for h, lab in ((60, "1m"), (180, "3m"), (300, "5m"), (900, "15m"), (1800, "30m"))
            }
        }
    cf = counterfactual
    if cf is None:
        # Do not trigger full CF here — use cached file
        cached = shadow_dir(campaign_root) / "counterfactual_research_latest.json"
        if cached.exists():
            try:
                cf = json.loads(cached.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                cf = {"status": "CACHE_UNAVAILABLE"}
        else:
            cf = {"status": "AWAITING_COUNTERFACTUAL"}

    fully_valid = sum(
        1 for e in (state.get("signals") or {}).values() if e.get("fully_matured_valid_all_horizons")
    )
    report = {
        "schema": "v30_shadow_quality_report_v1",
        "mode": "lightweight_index" if not run_heavy else "scheduled_scalar_stream",
        "runtime_commit": _git_commit(),
        "rss_mb": rss_mb(),
        "write_enabled": False,
        "close_only_MFE_removed": True,
        "historical_similar_setup_stats": None,
        "signals_unique": led.get("unique_signal_ids"),
        "signals_ledger_rows": led.get("ledger_rows"),
        "path_record_rows": idx.get("path_record_rows"),
        "unique_path_keys": idx.get("unique_path_keys"),
        "signals_fully_matured_valid_all_horizons": fully_valid,
        "valid_by_horizon": idx.get("valid_by_horizon"),
        "unavailable_by_horizon": idx.get("unavailable_by_horizon"),
        "per_horizon": horizon_pack.get("per_horizon"),
        "counterfactual": {
            "sample_counts": (cf or {}).get("sample_counts"),
            "mode": (cf or {}).get("mode"),
            "recommendation": (cf or {}).get("recommendation", "NO_AUTO_PROMOTION"),
        },
        "heavy_deferred": not run_heavy,
        "ready_for_demo_reenable": False,
        "auto_promotion": False,
    }
    out = shadow_dir(campaign_root) / "shadow_quality_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(out)
    return report
