#!/usr/bin/env python3
"""Stage 4 fixed-fleet multi-session read-only readiness review."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_per_symbol_summary import per_symbol_decision_counts  # noqa: E402
from tools.research.stage4_provider_stability_review import build_provider_stability_review  # noqa: E402
from tools.research.stage4_shadow_quality_summary import (  # noqa: E402
    build_shadow_quality_summary,
    load_shadow_summary,
    read_shadow_rows,
)

STAGE4_14B_DEFAULTS = {
    "duration_minutes": 360,
    "poll_interval_seconds": 300,
    "expected_tick_count": 72,
    "symbol_count": 4,
    "max_decisions": 288,
    "target_effective_decision_count": 240,
    "per_symbol_minimum": 50,
    "provider_chain_failed_max": 48,
}


def build_multi_session_readiness(
    session_summary: Dict[str, Any],
    *,
    session_id: str,
    shadow_quality: Optional[Dict[str, Any]] = None,
    provider_stability: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Multi-session readiness schema for fixed-fleet read-only runs."""
    provider_stability = provider_stability or build_provider_stability_review(session_summary)
    per_sym = per_symbol_decision_counts({"per_symbol": session_summary.get("per_symbol") or {}})
    if not per_sym:
        per_sym = {
            sym: int((session_summary.get("per_symbol") or {}).get(sym, {}).get("effective_decision_count") or 0)
            for sym in session_summary.get("symbols_configured") or session_summary.get("symbols") or []
        }

    shadow_quality_summary = shadow_quality or {}
    parse_errors = int(session_summary.get("parse_error_count") or 0)
    chain_failed = int(session_summary.get("provider_chain_failed_count") or 0)
    effective = int(session_summary.get("effective_decision_count") or 0)
    duration = float(session_summary.get("duration_minutes") or 180)

    readiness = (
        parse_errors == 0
        and bool(session_summary.get("dry_run_completed"))
        and effective >= int(session_summary.get("target_effective_decision_count") or 120)
        and chain_failed <= max(24, int(24 * (duration / 180.0)))
        and provider_stability.get("readiness_for_longer_run") is not False
    )

    return {
        "record_type": "stage4_multi_session_readiness",
        "session_id": session_id,
        "session_type": "fixed_fleet_read_only",
        "duration_minutes": duration,
        "symbols": list(session_summary.get("symbols_configured") or session_summary.get("symbols") or []),
        "effective_decision_count": effective,
        "per_symbol_decision_counts": per_sym,
        "provider_success_distribution": dict(session_summary.get("provider_success_distribution") or {}),
        "provider_chain_failed_count": chain_failed,
        "parse_error_count": parse_errors,
        "tick_count": int(session_summary.get("tick_count") or session_summary.get("actual_tick_count") or 0),
        "expected_tick_count": int(session_summary.get("expected_tick_count") or 0),
        "tick_drift_seconds_max": float(session_summary.get("tick_drift_seconds_max") or 0),
        "provider_stability_review": provider_stability,
        "shadow_quality_summary": shadow_quality_summary,
        "readiness_for_next_session": readiness,
        "generated_at_utc": utc_now_iso(),
    }


def build_414b_run_plan() -> Dict[str, Any]:
    d = STAGE4_14B_DEFAULTS
    return {
        "record_type": "stage4_414b_run_plan",
        "stage": "4.14b",
        "description": "fixed fleet 6h read-only soak",
        "duration_minutes": d["duration_minutes"],
        "poll_interval_seconds": d["poll_interval_seconds"],
        "expected_tick_count": d["expected_tick_count"],
        "symbol_count": d["symbol_count"],
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"],
        "max_decisions": d["max_decisions"],
        "target_effective_decision_count": d["target_effective_decision_count"],
        "pass_criteria": {
            "duration_minutes": d["duration_minutes"],
            "tick_count": d["expected_tick_count"],
            "expected_tick_count": d["expected_tick_count"],
            "effective_decision_count_min": d["target_effective_decision_count"],
            "dataset_target_met": True,
            "per_symbol_decision_counts_min": d["per_symbol_minimum"],
            "provider_chain_failed_count_max": d["provider_chain_failed_max"],
            "parse_error_count": 0,
            "validator_passed": True,
            "technical_valid": True,
            "mock_ai_used_count": 0,
            "order_sent_count": 0,
            "debug_log_has_api_key": False,
            "STAGE4_CLOUD_DRY_RUN_MINUTES_reset_to_0": True,
        },
        "env_recommendations": {
            "STAGE4_OUTPUT_DIR": "/data/stage4_ai_decisions_414b_fixed_fleet_360m",
            "STAGE4_CLOUD_DRY_RUN_MINUTES": "360",
            "STAGE4_POLL_INTERVAL_SECONDS": "300",
            "STAGE4_TARGET_EFFECTIVE_DECISION_COUNT": "240",
            "STAGE4_SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT,PEPEUSDT",
            "STAGE4_CEREBRAS_MAX_TOKENS": "1100",
        },
    }


def run_review(
    *,
    summary_path: Path,
    shadow_dirs: Optional[Dict[str, Path]] = None,
    session_id: str = "stage4_413d_fixed_fleet_180m",
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    shadow_dirs = shadow_dirs or {}
    per_symbol_summaries: Dict[str, Dict[str, Any]] = {}
    shadow_rows_by_symbol: Dict[str, List[Dict[str, Any]]] = {}

    for sym, shadow_dir in shadow_dirs.items():
        summary_file = shadow_dir / "stage4_shadow_compare_summary.json"
        if summary_file.is_file():
            per_symbol_summaries[sym] = load_shadow_summary(summary_file)
        rows_file = shadow_dir / "shadow_compare.jsonl"
        if rows_file.is_file():
            shadow_rows_by_symbol[sym] = read_shadow_rows(rows_file)

    provider_review = build_provider_stability_review(summary)
    shadow_quality = build_shadow_quality_summary(per_symbol_summaries, shadow_rows_by_symbol=shadow_rows_by_symbol)
    readiness = build_multi_session_readiness(
        summary,
        session_id=session_id,
        shadow_quality=shadow_quality,
        provider_stability=provider_review,
    )
    plan_414b = build_414b_run_plan()

    result = {
        "session_summary_path": str(summary_path),
        "provider_stability_review": provider_review,
        "shadow_quality_summary": shadow_quality,
        "multi_session_readiness": readiness,
        "stage_414b_run_plan": plan_414b,
        "readiness_for_414b_6h": readiness.get("readiness_for_next_session") is True,
    }
    if output_path:
        write_json(output_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4 multi-session readiness review")
    parser.add_argument("--summary", required=True, help="Path to stage4_ai_decision_summary.json")
    parser.add_argument("--session-id", default="stage4_413d_fixed_fleet_180m")
    parser.add_argument("--shadow-dir", action="append", default=[], help="SYMBOL=PATH shadow compare dir")
    parser.add_argument("--output", default="", help="Write combined review JSON here")
    args = parser.parse_args()

    shadow_dirs: Dict[str, Path] = {}
    for item in args.shadow_dir:
        if "=" not in item:
            continue
        sym, path = item.split("=", 1)
        shadow_dirs[sym.strip().upper()] = Path(path.strip())

    out = Path(args.output) if args.output else None
    result = run_review(
        summary_path=Path(args.summary),
        shadow_dirs=shadow_dirs or None,
        session_id=args.session_id,
        output_path=out,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("readiness_for_414b_6h") else 1


if __name__ == "__main__":
    raise SystemExit(main())
