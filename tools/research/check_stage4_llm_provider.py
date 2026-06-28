#!/usr/bin/env python3
"""Stage 4 LLM provider health check — minimal JSON probe, no orders."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.stage4_decision_schema import LLM_DECISION_FIELDS, parse_llm_decision  # noqa: E402
from tools.research.stage4_llm_client import Stage4LLMClient, groq_key_status  # noqa: E402

HEALTH_FIELDS = (
    "final_action",
    "candidate_side",
    "confidence",
    "why_skip",
)


def run_health_check(*, provider: str, model: str) -> dict:
    key_status = groq_key_status() if provider.strip().lower() == "groq" else {}
    client = Stage4LLMClient(provider=provider, model=model, load_env=True)
    avail = client.availability()
    if not avail.get("real_llm_available"):
        return {
            "provider_health_check_passed": False,
            "provider": provider,
            "model_name": model,
            "http_status": None,
            "raw_content_length": 0,
            "json_parse_ok": False,
            "required_fields_present": False,
            "error": avail.get("reason") or "provider_unavailable",
            **key_status,
        }

    messages = [
        {
            "role": "system",
            "content": (
                "You are a health-check probe. Respond with a single JSON object only. "
                f"Required keys: {', '.join(LLM_DECISION_FIELDS)}."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "final_action": "skip",
                    "symbol": "ETHUSDT",
                    "candidate_side": "NONE",
                    "confidence": 0.0,
                    "why_enter": "",
                    "why_skip": "health_check",
                    "side_reason": "probe",
                    "confidence_reason": "health_check",
                    "risk_notes": [],
                    "patch_awareness": "",
                    "uncertainty": "none",
                    "requires_manual_review": False,
                }
            ),
        },
    ]
    result = client.complete_json(messages, prompt_hash="health_check")
    parsed = result.get("parsed") or {}
    proposal, ok, err = parse_llm_decision(parsed, symbol="ETHUSDT")
    required_present = all(parsed.get(k) is not None for k in HEALTH_FIELDS) if parsed else False
    passed = (
        result.get("status") == "ok"
        and int(result.get("raw_content_length") or 0) > 0
        and ok
        and required_present
        and result.get("http_status") == 200
    )
    return {
        "provider_health_check_passed": passed,
        "provider": result.get("provider") or provider,
        "model_name": result.get("model") or model,
        "http_status": result.get("http_status"),
        "raw_content_length": result.get("raw_content_length", 0),
        "json_parse_ok": ok,
        "required_fields_present": required_present,
        "parse_error": err,
        "error_type": result.get("error_type"),
        "error": result.get("error"),
        "response_path_used": result.get("response_path_used"),
        "latency_ms": result.get("latency_ms"),
        **key_status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4 LLM provider health check")
    parser.add_argument("--provider", default="groq")
    parser.add_argument("--model", default="llama-3.3-70b-versatile")
    args = parser.parse_args()
    report = run_health_check(provider=args.provider.strip().lower(), model=args.model.strip())
    print(json.dumps(report, indent=2))
    return 0 if report.get("provider_health_check_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
