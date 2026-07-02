#!/usr/bin/env python3
"""Validate Stage 4 AI decision dry-run outputs."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_ai_decision_agent import (  # noqa: E402
    MOCK_MODEL_NAME,
    REQUIRED_DECISION_FIELDS,
    resolve_stage4_output_dir,
)
from tools.research.stage4_per_symbol_summary import (  # noqa: E402
    build_per_symbol_summary,
    per_symbol_chain_failed_counts,
)
from tools.research.stage4_system_events import read_system_events  # noqa: E402

ALLOWED_REAL_PROVIDERS = frozenset({"groq", "cerebras", "openai", "anthropic", "gemini"})

READINESS = ROOT / "data/external_alpha/reports/stage4_ai_decision_validation.json"

SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
)


def _aggregate_provider_stats(decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    provider_success: Dict[str, int] = {}
    fallback_reason_distribution: Dict[str, int] = {}
    fallback_used_count = 0
    mock_fallback_attempt_count = 0
    for d in decisions:
        if d.get("is_mock_ai") or d.get("fallback_to_mock"):
            mock_fallback_attempt_count += 1
        if d.get("fallback_used"):
            fallback_used_count += 1
            reason = str(d.get("fallback_reason") or "unknown")
            fallback_reason_distribution[reason] = fallback_reason_distribution.get(reason, 0) + 1
        if d.get("real_llm_used") and not d.get("parse_error") and not d.get("is_mock_ai"):
            prov = str(d.get("provider") or "unknown")
            provider_success[prov] = provider_success.get(prov, 0) + 1
    return {
        "provider_success_distribution": provider_success,
        "fallback_used_count": fallback_used_count,
        "fallback_reason_distribution": fallback_reason_distribution,
        "mock_fallback_attempt_count": mock_fallback_attempt_count,
    }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _read_summary(out: Path) -> Dict[str, Any]:
    path = out / "stage4_ai_decision_summary.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _debug_log_has_api_key(out: Path) -> bool:
    debug_path = out / "llm_client_debug.jsonl"
    if not debug_path.is_file():
        return False
    text = debug_path.read_text(encoding="utf-8", errors="replace")
    return any(pat.search(text) for pat in SECRET_PATTERNS)


def _compute_decision_metrics(decisions: List[Dict[str, Any]], summary: Dict[str, Any]) -> Dict[str, int]:
    parse_error_count = sum(1 for d in decisions if d.get("parse_error"))
    empty_response_count = sum(
        1
        for d in decisions
        if d.get("parse_error")
        and (
            d.get("raw_content_empty")
            or d.get("parse_error_type") in {"content_empty", "empty_llm_response", "rate_limit"}
        )
    )
    real_successful = sum(
        1 for d in decisions if d.get("real_llm_used") and not d.get("parse_error") and not d.get("is_mock_ai")
    )
    effective = real_successful
    return {
        "parse_error_count": summary.get("parse_error_count", parse_error_count),
        "empty_response_count": summary.get("empty_response_count", empty_response_count),
        "real_successful_llm_decision_count": summary.get("real_successful_llm_decision_count", real_successful),
        "effective_decision_count": summary.get("effective_decision_count", effective),
        "provider_rate_limit_count": int(summary.get("provider_rate_limit_count") or 0),
        "provider_error_count": int(summary.get("provider_error_count") or 0),
        "skipped_tick_count": int(summary.get("skipped_tick_count") or 0),
    }


def _target_effective_decision_count(summary: Dict[str, Any]) -> int:
    import os

    raw = summary.get("target_effective_decision_count")
    if raw is not None:
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            pass
    env_raw = os.environ.get("STAGE4_TARGET_EFFECTIVE_DECISION_COUNT", "30").strip()
    try:
        return max(1, int(float(env_raw)))
    except (TypeError, ValueError):
        return 30


def _apply_require_real_llm_checks(
    out: Path,
    *,
    decisions: List[Dict[str, Any]],
    summary: Dict[str, Any],
    technical_errors: List[str],
    metrics: Dict[str, int],
) -> None:
    real_count = sum(1 for d in decisions if d.get("real_llm_used"))
    mock_count = sum(1 for d in decisions if d.get("is_mock_ai"))
    if mock_count > 0:
        technical_errors.append("mock_ai_used_count_gt_zero")
    if summary.get("fallback_to_mock") is True or any(d.get("fallback_to_mock") for d in decisions):
        technical_errors.append("fallback_to_mock_true")
    if summary.get("model_name") == MOCK_MODEL_NAME or any(
        str(d.get("model_name") or "") == MOCK_MODEL_NAME for d in decisions
    ):
        technical_errors.append("model_name_mock_ai_decision_agent")

    debug_path = out / "llm_client_debug.jsonl"
    if not debug_path.is_file():
        technical_errors.append("llm_client_debug_jsonl_missing")
    elif _debug_log_has_api_key(out):
        technical_errors.append("debug_log_has_api_key")

    if metrics["parse_error_count"] > 0:
        technical_errors.append(f"parse_error_count_gt_zero:{metrics['parse_error_count']}")
    if metrics["empty_response_count"] > 0:
        technical_errors.append(f"empty_response_count_gt_zero:{metrics['empty_response_count']}")
    if metrics["real_successful_llm_decision_count"] <= 0:
        technical_errors.append("real_successful_llm_decision_count_zero")
    if metrics["effective_decision_count"] <= 0:
        technical_errors.append("effective_decision_count_zero")

    order_sent_count = sum(1 for d in decisions if d.get("order_sent"))
    if order_sent_count > 0:
        technical_errors.append("order_sent_count_gt_zero")

    if real_count == 0 and metrics["real_successful_llm_decision_count"] <= 0:
        technical_errors.append("real_llm_used_count_zero")

    for i, d in enumerate(decisions):
        if d.get("is_mock_ai"):
            technical_errors.append(f"decision_{i}_is_mock_ai_true")
        prov = str(d.get("provider") or "")
        if prov and prov not in ALLOWED_REAL_PROVIDERS:
            technical_errors.append(f"decision_{i}_provider_not_allowed:{prov}")

    provider_stats = _aggregate_provider_stats(decisions)
    if provider_stats["mock_fallback_attempt_count"] > 0:
        technical_errors.append("mock_fallback_attempt_count_gt_zero")

    provider_ok = summary.get("provider_health_check_passed")
    if provider_ok is False and _env_light_preflight() is False:
        technical_errors.append("provider_health_check_failed")


def _env_light_preflight() -> bool:
    import os

    raw = os.environ.get("STAGE4_LIGHT_PREFLIGHT", "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def validate(output_dir: Path | None = None, *, require_real_llm: bool = False) -> Dict[str, Any]:
    out = output_dir or resolve_stage4_output_dir()
    errors: List[str] = []
    technical_errors: List[str] = []
    decisions = _read_jsonl(out / "ai_decisions.jsonl")
    supervisor_rows = _read_jsonl(out / "risk_supervisor_decisions.jsonl")
    summary = _read_summary(out)
    metrics = _compute_decision_metrics(decisions, summary)
    target = _target_effective_decision_count(summary)
    dataset_target_met = metrics["effective_decision_count"] >= target

    if require_real_llm:
        _apply_require_real_llm_checks(
            out, decisions=decisions, summary=summary, technical_errors=technical_errors, metrics=metrics
        )
        errors.extend(technical_errors)
    elif not decisions:
        errors.append("decision_count_zero")
        technical_errors.append("decision_count_zero")

    for i, d in enumerate(decisions):
        for fld in REQUIRED_DECISION_FIELDS:
            if fld not in d:
                if fld == "real_llm_used" and d.get("is_mock_ai") and str(d.get("model_name") or "") == MOCK_MODEL_NAME:
                    continue
                errors.append(f"decision_{i}_missing_field:{fld}")
        if not str(d.get("symbol") or "").strip():
            technical_errors.append(f"decision_{i}_missing_symbol")
        if d.get("order_sent") is not False:
            errors.append(f"decision_{i}_order_sent_not_false")
        if require_real_llm and d.get("parse_error"):
            errors.append(f"decision_{i}_parse_error_true")
        src = str(d.get("decision_source") or "")
        if src not in {"ai_decision_agent", "mock_ai_decision_agent"}:
            errors.append(f"decision_{i}_invalid_decision_source:{src}")
        if not d.get("model_name") and not d.get("fallback_model_name"):
            errors.append(f"decision_{i}_missing_model_name")
        if not d.get("prompt_hash"):
            errors.append(f"decision_{i}_missing_prompt_hash")
        if not d.get("market_context"):
            errors.append(f"decision_{i}_missing_market_context")
        if not d.get("why_enter") and not d.get("why_skip"):
            errors.append(f"decision_{i}_missing_why_enter_or_why_skip")
        if not d.get("confidence_reason"):
            errors.append(f"decision_{i}_missing_confidence_reason")
        if "real_llm_used" not in d:
            legacy_mock = d.get("is_mock_ai") and str(d.get("model_name") or "") == MOCK_MODEL_NAME
            if not legacy_mock:
                errors.append(f"decision_{i}_missing_real_llm_used")
        if d.get("is_mock_ai") and d.get("real_llm_used"):
            errors.append(f"decision_{i}_mock_and_real_llm_conflict")
        if not d.get("risk_supervisor_result"):
            errors.append(f"decision_{i}_missing_risk_supervisor_result")
        patches = d.get("retrieved_patches") or []
        if patches and not d.get("patch_applied_before_decision"):
            errors.append(f"decision_{i}_patches_without_patch_applied_flag")

    real_count = sum(1 for d in decisions if d.get("real_llm_used"))
    mock_count = sum(1 for d in decisions if d.get("is_mock_ai"))
    order_sent_count = sum(1 for d in decisions if d.get("order_sent"))
    decision_missing_symbol_count = sum(1 for d in decisions if not str(d.get("symbol") or "").strip())
    provider_stats = _aggregate_provider_stats(decisions)
    system_events = read_system_events(out)
    symbols_configured = summary.get("symbols_configured") or summary.get("symbols") or []
    recomputed_fleet = build_per_symbol_summary(
        decisions,
        symbols_configured=symbols_configured,
        symbols_with_market_context_error=summary.get("symbols_with_market_context_error") or [],
        system_events=system_events,
    )
    per_symbol_failed = per_symbol_chain_failed_counts(recomputed_fleet)
    global_chain_failed = int(summary.get("provider_chain_failed_count") or 0)
    per_symbol_failed_sum = sum(per_symbol_failed.values())
    per_symbol_failed_sum_matches_global = per_symbol_failed_sum == global_chain_failed
    if require_real_llm and global_chain_failed > 0 and not per_symbol_failed_sum_matches_global:
        technical_errors.append(
            f"per_symbol_provider_chain_failed_sum_mismatch:{per_symbol_failed_sum}!={global_chain_failed}"
        )
    if decision_missing_symbol_count > 0:
        technical_errors.append(f"decision_missing_symbol_count_gt_zero:{decision_missing_symbol_count}")
    technical_valid = not technical_errors
    bundle_export = summary.get("bundle_export") or {}
    bundle_exported = bool(
        bundle_export.get("bundle_exported")
        or (bundle_export.get("bundle_safe") and bundle_export.get("file_count", 0) > 0)
    )

    passed = technical_valid
    return {
        "record_type": "stage4_ai_decision_output_validation",
        "generated_at_utc": utc_now_iso(),
        "output_dir": str(out),
        "passed": passed,
        "validator_passed": passed,
        "technical_valid": technical_valid,
        "dataset_target_met": dataset_target_met,
        "target_effective_decision_count": target,
        "errors": errors,
        "technical_errors": technical_errors,
        "require_real_llm": require_real_llm,
        "decision_count": len(decisions),
        "supervisor_decision_count": len(supervisor_rows),
        "all_order_sent_false": all(d.get("order_sent") is False for d in decisions) if decisions else True,
        "order_sent_count": order_sent_count,
        "real_llm_used_count": real_count,
        "mock_ai_used_count": mock_count,
        "real_llm_used": any(d.get("real_llm_used") for d in decisions) if decisions else False,
        "fallback_to_mock": any(d.get("fallback_to_mock") for d in decisions) if decisions else False,
        "dry_run_completed": summary.get("dry_run_completed"),
        "partial_completion": summary.get("partial_completion"),
        "failed_reason": summary.get("failed_reason"),
        "bundle_exported": bundle_exported,
        "debug_log_has_api_key": _debug_log_has_api_key(out),
        **metrics,
        **provider_stats,
        "provider_exhaustion_count": int(summary.get("provider_exhaustion_count") or 0),
        "fallback_attempt_count": int(summary.get("fallback_attempt_count") or 0),
        "fallback_success_count": int(summary.get("fallback_success_count") or 0),
        "provider_chain_failed_count": global_chain_failed,
        "per_symbol_summary_present": bool(summary.get("per_symbol") or recomputed_fleet.get("per_symbol")),
        "per_symbol_provider_chain_failed_counts": per_symbol_failed,
        "per_symbol_failed_sum_matches_global": per_symbol_failed_sum_matches_global,
        "decision_missing_symbol_count": decision_missing_symbol_count,
        "symbols_configured": summary.get("symbols_configured") or [],
        "symbols_seen": summary.get("symbols_seen") or recomputed_fleet.get("symbols_seen") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--require-real-llm", action="store_true")
    args = parser.parse_args()
    out = Path(args.output_dir) if args.output_dir else None
    result = validate(out, require_real_llm=args.require_real_llm)
    write_json(READINESS, result)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
