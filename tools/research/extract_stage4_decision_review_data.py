#!/usr/bin/env python3
"""Extract slim Stage 4 decision review data (no secrets, no full prompts)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _slim_decision(d: Dict[str, Any]) -> Dict[str, Any]:
    mc = d.get("market_context") or {}
    s3 = d.get("stage3_context_summary") or {}
    sr = d.get("risk_supervisor_result") or {}
    return {
        "decision_id": d.get("decision_id"),
        "created_at_utc": d.get("created_at_utc"),
        "symbol": d.get("symbol"),
        "provider": d.get("provider"),
        "model_name": d.get("model_name"),
        "decision_intent": d.get("decision_intent"),
        "final_action": d.get("final_action"),
        "final_decision": d.get("final_decision"),
        "confidence": d.get("confidence"),
        "regime": d.get("regime"),
        "stage3_context_available": d.get("stage3_context_available"),
        "recent_trade_results_count": d.get("recent_trade_results_count"),
        "recent_reflections_count": d.get("recent_reflections_count"),
        "active_patches_count": d.get("active_patches_count"),
        "matched_patch_count": d.get("matched_patch_count"),
        "patch_blocked": d.get("patch_blocked"),
        "patch_block_reason": d.get("patch_block_reason"),
        "matched_patch_actions": [str(p.get("action") or "") for p in (d.get("retrieved_patches") or [])],
        "why_skip": d.get("why_skip"),
        "why_enter": d.get("why_enter"),
        "side_reason": d.get("side_reason"),
        "confidence_reason": d.get("confidence_reason"),
        "patch_awareness": d.get("patch_awareness"),
        "uncertainty": d.get("uncertainty"),
        "risk_factors": d.get("risk_factors"),
        "edge_factors": d.get("edge_factors"),
        "missing_data": d.get("missing_data"),
        "parse_error": d.get("parse_error"),
        "is_mock_ai": d.get("is_mock_ai"),
        "fallback_used": d.get("fallback_used"),
        "order_sent": d.get("order_sent"),
        "risk_supervisor_veto_reason": sr.get("veto_reason"),
        "risk_supervisor_approved": sr.get("approved"),
        "market_context": {
            "regime": mc.get("regime"),
            "regime_reason": mc.get("regime_reason"),
            "trend_strength": mc.get("trend_strength"),
            "range_strength": mc.get("range_strength"),
            "volatility_level": mc.get("volatility_level"),
            "change_24h_pct": mc.get("change_24h_pct"),
            "trend_15m": mc.get("trend_15m"),
            "volatility_15m": mc.get("volatility_15m"),
            "data_quality": mc.get("data_quality"),
            "kline_data_quality": mc.get("kline_data_quality"),
        },
        "stage3_context_summary": {
            "stage3_context_available": s3.get("stage3_context_available"),
            "recent_trade_results_count": s3.get("recent_trade_results_count"),
            "recent_reflections_count": s3.get("recent_reflections_count"),
            "active_patches_count": s3.get("active_patches_count"),
            "active_patches_actions": [p.get("action") for p in (s3.get("active_patches") or [])[:5]],
            "recent_trade_pnl_summary": [
                {
                    "side": t.get("side"),
                    "close_pnl": t.get("close_pnl"),
                    "failure_reason": t.get("failure_reason"),
                }
                for t in (s3.get("recent_trade_results") or [])[:5]
            ],
            "recent_reflection_summary": [
                {
                    "failure_reason": r.get("failure_reason"),
                    "patch_action": r.get("patch_action"),
                }
                for r in (s3.get("recent_reflections") or [])[:5]
            ],
        },
    }


def extract(output_dir: Path) -> Dict[str, Any]:
    summary_path = output_dir / "stage4_ai_decision_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    decisions: List[Dict[str, Any]] = []
    dec_path = output_dir / "ai_decisions.jsonl"
    if dec_path.is_file():
        for line in dec_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                decisions.append(_slim_decision(json.loads(line)))
    events: List[Dict[str, Any]] = []
    ev_path = output_dir / "stage4_system_events.jsonl"
    if ev_path.is_file():
        for line in ev_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                events.append(
                    {k: e.get(k) for k in ("event_type", "provider", "symbol", "tick_index", "action", "order_sent")}
                )
    debug_rows: List[Dict[str, Any]] = []
    dbg_path = output_dir / "llm_client_debug.jsonl"
    if dbg_path.is_file():
        for line in dbg_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                debug_rows.append(
                    {
                        k: r.get(k)
                        for k in (
                            "created_at_utc",
                            "provider",
                            "model_name",
                            "success",
                            "http_status",
                            "error_type",
                            "call_kind",
                            "raw_content_length",
                        )
                    }
                )
    return {
        "output_dir": str(output_dir),
        "summary": summary,
        "decisions": decisions,
        "system_events": events,
        "debug_rows": debug_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    data = extract(Path(args.output_dir))
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
