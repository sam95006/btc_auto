#!/usr/bin/env python3
"""Validate Stage 4 AI decision dry-run outputs."""
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
from tools.research.stage4_ai_decision_agent import (  # noqa: E402
    MOCK_MODEL_NAME,
    REQUIRED_DECISION_FIELDS,
    resolve_stage4_output_dir,
)

READINESS = ROOT / "data/external_alpha/reports/stage4_ai_decision_validation.json"


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


def _apply_require_real_llm_checks(
    out: Path,
    *,
    decisions: List[Dict[str, Any]],
    summary: Dict[str, Any],
    errors: List[str],
) -> None:
    if summary.get("dry_run_completed") is False:
        errors.append(f"dry_run_failed:{summary.get('failed_reason') or 'unknown'}")

    real_count = sum(1 for d in decisions if d.get("real_llm_used"))
    mock_count = sum(1 for d in decisions if d.get("is_mock_ai"))
    if real_count == 0:
        errors.append("real_llm_used_count_zero")
    if mock_count > 0:
        errors.append("mock_ai_used_count_gt_zero")
    if summary.get("fallback_to_mock") is True or any(d.get("fallback_to_mock") for d in decisions):
        errors.append("fallback_to_mock_true")
    if summary.get("model_name") == MOCK_MODEL_NAME or any(
        str(d.get("model_name") or "") == MOCK_MODEL_NAME for d in decisions
    ):
        errors.append("model_name_mock_ai_decision_agent")

    debug_path = out / "llm_client_debug.jsonl"
    if not debug_path.is_file():
        errors.append("llm_client_debug_jsonl_missing")

    provider_ok = summary.get("provider_health_check_passed")
    if provider_ok is False:
        errors.append("provider_health_check_failed")
    elif provider_ok is None:
        from tools.research.check_stage4_llm_provider import run_health_check

        provider = str(summary.get("provider") or "groq")
        model = str(summary.get("model_name") or "llama-3.3-70b-versatile")
        health = run_health_check(provider=provider, model=model)
        if not health.get("provider_health_check_passed"):
            errors.append("provider_health_check_failed")


def validate(output_dir: Path | None = None, *, require_real_llm: bool = False) -> Dict[str, Any]:
    out = output_dir or resolve_stage4_output_dir()
    errors: List[str] = []
    decisions = _read_jsonl(out / "ai_decisions.jsonl")
    supervisor_rows = _read_jsonl(out / "risk_supervisor_decisions.jsonl")
    summary = _read_summary(out)

    if require_real_llm:
        _apply_require_real_llm_checks(out, decisions=decisions, summary=summary, errors=errors)
    elif not decisions:
        errors.append("decision_count_zero")

    for i, d in enumerate(decisions):
        for fld in REQUIRED_DECISION_FIELDS:
            if fld not in d:
                if fld == "real_llm_used" and d.get("is_mock_ai") and str(d.get("model_name") or "") == MOCK_MODEL_NAME:
                    continue
                errors.append(f"decision_{i}_missing_field:{fld}")
        if d.get("order_sent") is not False:
            errors.append(f"decision_{i}_order_sent_not_false")
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

    passed = not errors
    return {
        "record_type": "stage4_ai_decision_output_validation",
        "generated_at_utc": utc_now_iso(),
        "output_dir": str(out),
        "passed": passed,
        "errors": errors,
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
        "failed_reason": summary.get("failed_reason"),
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
