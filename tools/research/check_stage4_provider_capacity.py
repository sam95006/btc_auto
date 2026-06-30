#!/usr/bin/env python3
"""Stage 4 provider capacity check — read-only, no orders, no mock."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.stage4_decision_schema import parse_llm_decision  # noqa: E402
from tools.research.stage4_groq_key_registry import GroqKeyRegistry, probe_groq_keys  # noqa: E402
from tools.research.stage4_llm_client import Stage4LLMClient, _load_local_env  # noqa: E402

SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),
    re.compile(r"csk-[A-Za-z0-9]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
)


def _text_has_secret(text: str) -> bool:
    return any(pat.search(text) for pat in SECRET_PATTERNS)


def _probe_cerebras_direct(*, model: str) -> Dict[str, Any]:
    key_present = bool((os.environ.get("CEREBRAS_API_KEY") or "").strip())
    if not key_present:
        return {
            "cerebras_available": False,
            "cerebras_valid_json": False,
            "cerebras_error_type": "missing_api_key",
            "cerebras_model": model,
            "cerebras_direct_success": False,
            "cerebras_error_distribution": {},
        }
    client = Stage4LLMClient(provider="cerebras", model=model, load_env=False)
    avail = client.availability()
    if not avail.get("real_llm_available"):
        return {
            "cerebras_available": False,
            "cerebras_valid_json": False,
            "cerebras_error_type": avail.get("reason") or "llm_unavailable",
            "cerebras_model": model,
            "cerebras_direct_success": False,
            "cerebras_error_distribution": {},
        }
    messages = [
        {
            "role": "system",
            "content": "Respond with one JSON object only.",
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
                    "why_skip": "capacity_probe",
                    "side_reason": "probe",
                    "confidence_reason": "probe",
                    "risk_notes": [],
                    "patch_awareness": "",
                    "uncertainty": "none",
                    "requires_manual_review": False,
                }
            ),
        },
    ]
    result = client.complete_json(
        messages,
        prompt_hash="capacity_probe_cerebras",
        call_kind="capacity_probe",
        use_rate_gate=False,
    )
    err = str(result.get("error_type") or "")
    parsed = result.get("parsed") or {}
    _, ok, _ = parse_llm_decision(parsed, symbol="ETHUSDT")
    valid = result.get("status") == "ok" and ok and int(result.get("raw_content_length") or 0) > 0
    error_distribution: Dict[str, int] = {}
    if not valid and err:
        error_distribution[err] = 1
    return {
        "cerebras_available": True,
        "cerebras_valid_json": valid,
        "cerebras_error_type": None if valid else (err or "unknown"),
        "cerebras_model": model,
        "cerebras_direct_success": valid,
        "cerebras_error_distribution": error_distribution,
        "provider": "cerebras",
        "model_name": model,
        "is_mock_ai": False,
        "parse_error": not ok,
        "order_sent": False,
        "http_status": result.get("http_status"),
    }


def run_capacity_check(
    *,
    output_path: Path | None = None,
    provider: str = "full",
) -> Dict[str, Any]:
    GroqKeyRegistry.reset_shared()
    mode = (provider or "full").strip().lower()
    groq: Dict[str, Any] = {}
    cerebras: Dict[str, Any] = {}
    if mode in {"full", "groq", "all"}:
        groq = probe_groq_keys()
    if mode in {"full", "cerebras", "all"}:
        cerebras_model = (
            os.environ.get("STAGE4_CEREBRAS_LLM_MODEL")
            or os.environ.get("STAGE4_SECONDARY_LLM_MODEL")
            or "gpt-oss-120b"
        ).strip()
        cerebras = _probe_cerebras_direct(model=cerebras_model)
    elif mode == "groq":
        cerebras_model = (
            os.environ.get("STAGE4_CEREBRAS_LLM_MODEL")
            or os.environ.get("STAGE4_SECONDARY_LLM_MODEL")
            or "gpt-oss-120b"
        ).strip()
        cerebras = {
            "cerebras_available": False,
            "cerebras_valid_json": False,
            "cerebras_direct_success": False,
            "cerebras_error_type": "skipped_groq_only_probe",
            "cerebras_error_distribution": {},
        }
    else:
        cerebras_model = (
            os.environ.get("STAGE4_CEREBRAS_LLM_MODEL")
            or os.environ.get("STAGE4_SECONDARY_LLM_MODEL")
            or "gpt-oss-120b"
        ).strip()

    groq_available = int(groq.get("groq_valid_key_count") or 0) > 0
    groq_valid_json = bool(groq.get("groq_valid_key_count"))
    groq_direct_success = groq_valid_json
    cerebras_key_present = bool((os.environ.get("CEREBRAS_API_KEY") or "").strip())
    if mode == "groq":
        can_start = groq_direct_success and int(groq.get("groq_invalid_key_count") or 0) == 0
    else:
        can_start = bool(groq_direct_success or cerebras.get("cerebras_direct_success"))
    report: Dict[str, Any] = {
        "probe_mode": mode,
        "groq_available": groq_available,
        "groq_valid_json": groq_valid_json,
        "groq_direct_success": groq_direct_success,
        "groq_error_type": next(iter(groq.get("groq_error_distribution") or {}), None),
        "groq_valid_key_count": int(groq.get("groq_valid_key_count") or 0),
        "groq_invalid_key_count": int(groq.get("groq_invalid_key_count") or 0),
        "groq_rate_limited_key_count": int(groq.get("groq_rate_limited_key_count") or 0),
        "groq_key_count": int(groq.get("groq_key_count") or 0),
        "groq_error_distribution": groq.get("groq_error_distribution") or {},
        "groq_keys": groq.get("groq_keys") or [],
        "cerebras_api_key_present": cerebras_key_present,
        "cerebras_available": cerebras.get("cerebras_available"),
        "cerebras_valid_json": cerebras.get("cerebras_valid_json"),
        "cerebras_error_type": cerebras.get("cerebras_error_type"),
        "cerebras_model": cerebras_model if mode != "groq" else (
            os.environ.get("STAGE4_CEREBRAS_LLM_MODEL")
            or os.environ.get("STAGE4_SECONDARY_LLM_MODEL")
            or "gpt-oss-120b"
        ).strip(),
        "cerebras_direct_success": cerebras.get("cerebras_direct_success"),
        "cerebras_error_distribution": cerebras.get("cerebras_error_distribution") or {},
        "mock_used": False,
        "order_sent": False,
        "can_start_long_soak": can_start,
        "provider_capacity_ok": can_start,
    }
    serialized = json.dumps(report, ensure_ascii=False)
    report["debug_log_has_api_key"] = _text_has_secret(serialized)
    if output_path is None:
        custom = os.environ.get("STAGE4_OUTPUT_DIR", "").strip()
        base = Path(custom) if custom else ROOT / "data" / "external_alpha" / "stage4_ai_decisions"
        base.mkdir(parents=True, exist_ok=True)
        output_path = base / "provider_capacity_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["provider_capacity_report_path"] = str(output_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4 provider capacity check (read-only)")
    parser.add_argument("--output", default="", help="Output JSON path")
    parser.add_argument(
        "--provider",
        default="full",
        choices=("full", "groq", "cerebras", "all"),
        help="Probe scope: full (default), groq-only, cerebras-only",
    )
    args = parser.parse_args()
    _load_local_env()
    out = Path(args.output) if args.output else None
    report = run_capacity_check(output_path=out, provider=args.provider)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("can_start_long_soak") else 1


if __name__ == "__main__":
    raise SystemExit(main())
