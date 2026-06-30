#!/usr/bin/env python3
"""Stage 4 prompt token budget review — character breakdown, no secrets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.stage4_prompt_builder import (  # noqa: E402
    OUTPUT_SCHEMA_HINT,
    SYSTEM_PROMPT,
    build_decision_prompt,
)


def _estimate_tokens(chars: int) -> int:
    return max(1, int(chars / 4))


def _section_chars(payload: Dict[str, Any]) -> Dict[str, int]:
    import json as _json

    s3 = payload.get("stage3_context") or {}
    return {
        "system_prompt_chars": len(SYSTEM_PROMPT),
        "user_prompt_chars": len(_json.dumps(payload, ensure_ascii=False)),
        "stage3_context_chars": len(_json.dumps(s3, ensure_ascii=False)),
        "market_context_chars": len(_json.dumps(payload.get("market_context") or {}, ensure_ascii=False)),
        "active_patches_chars": len(_json.dumps(payload.get("retrieved_patches") or [], ensure_ascii=False)),
        "recent_reflections_chars": len(_json.dumps(payload.get("recent_reflections") or [], ensure_ascii=False)),
        "recent_trades_chars": len(_json.dumps(payload.get("recent_trade_results") or [], ensure_ascii=False)),
        "schema_hint_chars": len(_json.dumps(OUTPUT_SCHEMA_HINT, ensure_ascii=False)),
    }


def analyze_from_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    messages = build_decision_prompt(
        symbol=str(decision.get("symbol") or "ETHUSDT"),
        market_context=decision.get("market_context") or {},
        account_context=decision.get("account_context") or {},
        retrieved_patches=decision.get("retrieved_patches") or [],
        recent_trade_results=decision.get("recent_trade_results") or [],
        recent_reflections=decision.get("recent_reflections") or [],
        safety_constraints=decision.get("safety_constraints") or {},
        current_open_positions=int(decision.get("current_open_positions") or 0),
        stage3_context=decision.get("stage3_context_summary") or {},
    )
    user_blob = next((m["content"] for m in messages if m.get("role") == "user"), "")
    user_payload = json.loads(user_blob) if user_blob else {}
    sections = _section_chars(
        {
            "market_context": user_payload.get("market_context"),
            "retrieved_patches": user_payload.get("retrieved_patches"),
            "recent_reflections": user_payload.get("recent_reflections"),
            "recent_trade_results": user_payload.get("recent_trade_results"),
            "stage3_context": {
                "stage3_context_available": user_payload.get("stage3_context_available"),
                "stage3_context_reason": user_payload.get("stage3_context_reason"),
            },
        }
    )
    total_chars = sum(len(m.get("content") or "") for m in messages)
    max_completion = int(__import__("os").environ.get("NEXUS_LLM_MAX_COMPLETION_TOKENS", "700"))
    recommendations = [
        "active_patches: cap at top 3 by relevance",
        "recent_reflections: cap at 3 most recent",
        "recent_trade_results: cap at 3-5 most recent",
        "market_context: drop low-signal fields if duplicated in regime summary",
        "instructions: dedupe schema hints already in SYSTEM_PROMPT",
        f"max_tokens: current NEXUS_LLM_MAX_COMPLETION_TOKENS={max_completion}; consider 400-500 for skip-heavy dry-run",
        "Groq: keep json_object mode; do not use json_schema",
        "Cerebras: use max_tokens only (no max_completion_tokens duplicate)",
    ]
    if sections["active_patches_chars"] > 800:
        recommendations.insert(0, "HIGH: active_patches section is large — trim to top 3")
    if sections["recent_reflections_chars"] > 1200:
        recommendations.insert(0, "HIGH: reflections section is large — trim to 3")
    return {
        "record_type": "stage4_prompt_budget_review",
        "system_prompt_chars": sections["system_prompt_chars"],
        "user_prompt_chars": sections["user_prompt_chars"],
        "stage3_context_chars": sections["stage3_context_chars"],
        "market_context_chars": sections["market_context_chars"],
        "active_patches_chars": sections["active_patches_chars"],
        "recent_reflections_chars": sections["recent_reflections_chars"],
        "recent_trades_chars": sections["recent_trades_chars"],
        "schema_hint_chars": sections["schema_hint_chars"],
        "total_prompt_chars": total_chars,
        "estimated_prompt_tokens": _estimate_tokens(total_chars),
        "estimated_output_tokens_max": max_completion,
        "estimated_total_tokens_per_call": _estimate_tokens(total_chars) + max_completion,
        "active_patches_count": len(user_payload.get("retrieved_patches") or []),
        "recent_reflections_count": len(user_payload.get("recent_reflections") or []),
        "recent_trades_count": len(user_payload.get("recent_trade_results") or []),
        "prompt_compression_recommendation": recommendations,
    }


def analyze_prompt_budget(output_dir: Path) -> Dict[str, Any]:
    out = output_dir.expanduser().resolve()
    dec_path = out / "ai_decisions.jsonl"
    if not dec_path.is_file():
        return {"record_type": "stage4_prompt_budget_review", "error": "no_decisions_file"}
    decisions: List[Dict[str, Any]] = []
    for line in dec_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            decisions.append(json.loads(line))
    if not decisions:
        return {"record_type": "stage4_prompt_budget_review", "error": "empty_decisions"}
    samples = [analyze_from_decision(d) for d in decisions[:3]]
    avg_prompt = sum(s["estimated_prompt_tokens"] for s in samples) / len(samples)
    avg_chars = sum(s["total_prompt_chars"] for s in samples) / len(samples)
    merged = samples[0].copy()
    merged["samples_analyzed"] = len(samples)
    merged["average_estimated_prompt_tokens"] = round(avg_prompt, 1)
    merged["average_total_prompt_chars"] = round(avg_chars, 1)
    merged["prompt_budget_report_created"] = True
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4 prompt token budget review")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--write", default="")
    args = parser.parse_args()
    report = analyze_prompt_budget(Path(args.output_dir))
    if args.write:
        p = Path(args.write)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
