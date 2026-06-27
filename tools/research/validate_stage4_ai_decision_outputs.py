#!/usr/bin/env python3
"""Validate Stage 4 AI decision dry-run outputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_ai_decision_agent import REQUIRED_DECISION_FIELDS, resolve_stage4_output_dir  # noqa: E402

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


def validate(output_dir: Path | None = None) -> Dict[str, Any]:
    out = output_dir or resolve_stage4_output_dir()
    errors: List[str] = []
    decisions = _read_jsonl(out / "ai_decisions.jsonl")
    supervisor_rows = _read_jsonl(out / "risk_supervisor_decisions.jsonl")

    if not decisions:
        errors.append("decision_count_zero")

    for i, d in enumerate(decisions):
        for fld in REQUIRED_DECISION_FIELDS:
            if fld not in d:
                if fld == "real_llm_used" and d.get("is_mock_ai") and str(d.get("model_name") or "") == "mock_ai_decision_agent":
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
            legacy_mock = d.get("is_mock_ai") and str(d.get("model_name") or "") == "mock_ai_decision_agent"
            if not legacy_mock:
                errors.append(f"decision_{i}_missing_real_llm_used")
        if d.get("is_mock_ai") and d.get("real_llm_used"):
            errors.append(f"decision_{i}_mock_and_real_llm_conflict")
        if not d.get("risk_supervisor_result"):
            errors.append(f"decision_{i}_missing_risk_supervisor_result")
        patches = d.get("retrieved_patches") or []
        if patches and not d.get("patch_applied_before_decision"):
            errors.append(f"decision_{i}_patches_without_patch_applied_flag")

    passed = not errors
    return {
        "record_type": "stage4_ai_decision_output_validation",
        "generated_at_utc": utc_now_iso(),
        "output_dir": str(out),
        "passed": passed,
        "errors": errors,
        "decision_count": len(decisions),
        "supervisor_decision_count": len(supervisor_rows),
        "all_order_sent_false": all(d.get("order_sent") is False for d in decisions) if decisions else False,
        "real_llm_used": any(d.get("real_llm_used") for d in decisions) if decisions else False,
        "fallback_to_mock": any(d.get("fallback_to_mock") for d in decisions) if decisions else False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    out = Path(args.output_dir) if args.output_dir else None
    result = validate(out)
    write_json(READINESS, result)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
