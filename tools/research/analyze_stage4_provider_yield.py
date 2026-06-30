#!/usr/bin/env python3
"""Stage 4 provider yield diagnosis — Groq 429, Cerebras fallback, token estimates."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.stage4_response_parser import safe_excerpt  # noqa: E402

TICK_RE = re.compile(r"TICK=(\d+)")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _estimate_tokens(chars: int) -> int:
    return max(1, int(chars / 4))


def _parse_dry_run_log(log_path: Path) -> Dict[str, Any]:
    ticks_success: List[int] = []
    ticks_skipped: List[int] = []
    ticks_429: List[int] = []
    if not log_path.is_file():
        return {
            "ticks_success": ticks_success,
            "ticks_skipped": ticks_skipped,
            "ticks_429": ticks_429,
        }
    for line in log_path.read_text(encoding="utf-8").splitlines():
        m = TICK_RE.search(line)
        if not m:
            continue
        tick = int(m.group(1))
        if "SKIPPED" in line and "provider_chain_failed" in line:
            ticks_skipped.append(tick)
        elif "final=" in line and "parse_error=False" in line:
            ticks_success.append(tick)
        if "429" in line or "rate_limit" in line.lower():
            ticks_429.append(tick)
    return {
        "ticks_success": ticks_success,
        "ticks_skipped": ticks_skipped,
        "ticks_429": ticks_429,
    }


def _classify_groq_429(msg: str, err_type: str) -> str:
    blob = f"{msg} {err_type}".lower()
    if "tokens per minute" in blob or "tpm" in blob or err_type == "tokens":
        return "TPM token quota"
    if "requests per minute" in blob or "rpm" in blob:
        return "RPM request quota"
    if "requests per day" in blob or "rpd" in blob or "daily" in blob:
        return "RPD daily quota"
    if "rate limit" in blob and "token" in blob:
        return "TPM token quota"
    if "quota" in blob and "project" in blob:
        return "project quota"
    if "quota" in blob:
        return "single key quota"
    if err_type in {"rate_limit", "tokens"}:
        return "TPM token quota"
    return "unknown"


def analyze_provider_yield(output_dir: Path) -> Dict[str, Any]:
    out = output_dir.expanduser().resolve()
    summary: Dict[str, Any] = {}
    summary_path = out / "stage4_ai_decision_summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    debug = _read_jsonl(out / "llm_client_debug.jsonl")
    decisions = _read_jsonl(out / "ai_decisions.jsonl")
    events = _read_jsonl(out / "stage4_system_events.jsonl")
    log_info = _parse_dry_run_log(out / "stage4_30m_dry_run.log")

    groq_debug = [r for r in debug if str(r.get("provider") or "") == "groq"]
    cerebras_debug = [r for r in debug if str(r.get("provider") or "") == "cerebras"]
    groq_429_rows = [r for r in groq_debug if int(r.get("http_status") or 0) == 429]
    groq_success = [r for r in groq_debug if r.get("success")]

    groq_429_messages: List[str] = []
    groq_429_types: List[str] = []
    for row in groq_429_rows:
        msg = str(row.get("error_message_safe") or row.get("error_type") or "")
        if msg:
            groq_429_messages.append(msg)
        et = str(row.get("error_type") or "")
        if et:
            groq_429_types.append(et)

    # provider_attempts from skipped events and decisions
    cerebras_attempts: List[Dict[str, Any]] = []
    groq_attempts_failed: List[Dict[str, Any]] = []
    for ev in events:
        if str(ev.get("event_type") or "") != "tick_skipped":
            continue
        for att in ev.get("provider_attempts") or []:
            prov = str(att.get("provider") or "")
            if prov == "cerebras":
                cerebras_attempts.append(att)
            elif prov == "groq" and att.get("result") != "success":
                groq_attempts_failed.append(att)
    for d in decisions:
        for att in d.get("provider_attempts") or []:
            prov = str(att.get("provider") or "")
            if prov == "cerebras" and att.get("result") != "success":
                if att not in cerebras_attempts:
                    cerebras_attempts.append(att)

    cerebras_err_dist = Counter(
        str(a.get("error_type") or a.get("result") or "unknown") for a in cerebras_attempts
    )
    cerebras_http_dist = Counter(int(a.get("http_status") or 0) for a in cerebras_attempts if a.get("http_status"))

    output_lengths = [int(r.get("raw_content_length") or 0) for r in groq_success if r.get("raw_content_length")]
    avg_output_chars = sum(output_lengths) / len(output_lengths) if output_lengths else 0
    max_output_chars = max(output_lengths) if output_lengths else 0

    # Estimate input tokens from first decision prompt rebuild if available
    prompt_chars = 0
    if decisions:
        d0 = decisions[0]
        try:
            from tools.research.stage4_prompt_builder import build_decision_prompt

            messages = build_decision_prompt(
                symbol=str(d0.get("symbol") or "ETHUSDT"),
                market_context=d0.get("market_context") or {},
                account_context=d0.get("account_context") or {},
                retrieved_patches=d0.get("retrieved_patches") or [],
                recent_trade_results=d0.get("recent_trade_results") or [],
                recent_reflections=d0.get("recent_reflections") or [],
                safety_constraints=d0.get("safety_constraints") or {},
                current_open_positions=int(d0.get("current_open_positions") or 0),
                stage3_context=d0.get("stage3_context_summary") or {},
            )
            prompt_chars = sum(len(m.get("content") or "") for m in messages)
        except Exception:
            prompt_chars = 0

    est_input_tokens = _estimate_tokens(prompt_chars) if prompt_chars else 0
    est_output_tokens = [_estimate_tokens(n) for n in output_lengths]
    total_per_decision = [
        est_input_tokens + ot for ot in est_output_tokens
    ] if est_input_tokens and est_output_tokens else []

    first_429_tick = min(log_info["ticks_skipped"]) if log_info["ticks_skipped"] else None
    if groq_429_rows and log_info["ticks_success"]:
        # approximate: first skip after last success before skip streak
        success_set = set(log_info["ticks_success"])
        skipped = sorted(log_info["ticks_skipped"])
        first_429_tick = skipped[0] if skipped else None
        successes_before = [t for t in log_info["ticks_success"] if first_429_tick and t < first_429_tick]
        est_tokens_before_429 = len(successes_before) * (est_input_tokens + int(avg_output_chars / 4)) if est_input_tokens else 0
    else:
        successes_before = log_info["ticks_success"]
        est_tokens_before_429 = len(successes_before) * (est_input_tokens + int(avg_output_chars / 4)) if est_input_tokens else 0

    groq_429_msg_safe = safe_excerpt(groq_429_messages[0], 200) if groq_429_messages else None
    groq_429_err_type = groq_429_types[0] if groq_429_types else (
        str((summary.get("groq_keys") or [{}])[0].get("last_error_type") or "")
    )
    groq_429_root = _classify_groq_429(groq_429_msg_safe or "", groq_429_err_type)

    cerebras_root = "no_cerebras_attempts"
    if cerebras_attempts:
        top_err = cerebras_err_dist.most_common(1)[0][0] if cerebras_err_dist else "unknown"
        top_http = cerebras_http_dist.most_common(1)[0][0] if cerebras_http_dist else 0
        if top_http == 400:
            cerebras_root = "http_400_invalid_request_check_payload_shape"
        elif top_http == 404:
            cerebras_root = "http_404_model_not_found"
        elif top_http == 429 or top_err == "rate_limit":
            cerebras_root = "rate_limit"
        elif top_err in {"json_parse_failed", "content_empty"}:
            cerebras_root = "response_parse_or_empty"
        else:
            cerebras_root = f"{top_err}_http_{top_http}"

    return {
        "record_type": "stage4_provider_yield_diagnosis",
        "output_dir": str(out),
        "groq_429_count": int(summary.get("groq_429_count") or len(groq_429_rows)),
        "groq_429_first_tick": first_429_tick,
        "groq_429_last_tick": max(log_info["ticks_skipped"]) if log_info["ticks_skipped"] else None,
        "groq_429_error_message_safe": groq_429_msg_safe,
        "groq_429_last_error_type": groq_429_err_type or None,
        "groq_429_root_cause": groq_429_root,
        "input_tokens_per_successful_tick": est_input_tokens,
        "output_tokens_per_successful_tick": int(avg_output_chars / 4) if avg_output_chars else 0,
        "total_tokens_per_successful_tick": int(est_input_tokens + avg_output_chars / 4) if est_input_tokens else 0,
        "average_tokens_per_decision": round(sum(total_per_decision) / len(total_per_decision), 1) if total_per_decision else 0,
        "max_tokens_per_decision": max(total_per_decision) if total_per_decision else 0,
        "estimated_tokens_before_first_429": int(est_tokens_before_429),
        "prompt_chars_estimated_from_sample_decision": prompt_chars,
        "cerebras_attempt_count": int(summary.get("cerebras_attempt_count") or len(cerebras_attempts)),
        "cerebras_success_count": int(summary.get("cerebras_success_count") or 0),
        "cerebras_failure_error_distribution": dict(cerebras_err_dist),
        "cerebras_failure_http_distribution": {str(k): v for k, v in cerebras_http_dist.items()},
        "cerebras_fallback_root_cause": cerebras_root,
        "cerebras_debug_rows": len(cerebras_debug),
        "provider_chain_failed_count": int(summary.get("provider_chain_failed_count") or 0),
        "effective_decision_count": int(summary.get("effective_decision_count") or len(decisions)),
        "tick_count": int(summary.get("tick_count") or 0),
        "mock_ai_used_count": int(summary.get("mock_ai_used_count") or 0),
        "order_sent_count": int(summary.get("order_sent_count") or 0),
        "parse_error_count": int(summary.get("parse_error_count") or 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Stage 4 provider yield")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--write", default="", help="Optional JSON output path")
    args = parser.parse_args()
    report = analyze_provider_yield(Path(args.output_dir))
    if args.write:
        p = Path(args.write)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report["report_path"] = str(p)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
