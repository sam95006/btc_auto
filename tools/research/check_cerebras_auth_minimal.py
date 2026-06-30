#!/usr/bin/env python3
"""Minimal Cerebras auth + payload matrix probe — direct HTTP, no secrets in output."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.stage4_cerebras_payload import (  # noqa: E402
    CEREBRAS_CHAT_URL,
    DEFAULT_CEREBRAS_MODEL,
    PAYLOAD_VARIANTS,
    build_cerebras_payload_variant,
    build_stage4_cerebras_openai_payload,
    cerebras_payload_metadata,
    classify_http_status,
    parse_groq_error_safe,
)
from tools.research.stage4_response_parser import safe_excerpt  # noqa: E402

SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),
    re.compile(r"csk-[A-Za-z0-9]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
)


def _fingerprint(key: str) -> str:
    if not key:
        return ""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _text_has_secret(text: str) -> bool:
    return any(pat.search(text) for pat in SECRET_PATTERNS)


def _clean_key(raw: str) -> str:
    return raw.strip().strip('"').strip("'")


def _cerebras_post(*, api_key: str, payload: Dict[str, Any]) -> Tuple[int, str]:
    from tools.research.stage4_llm_client import HTTP_HEADERS_BASE

    body = json.dumps(payload).encode("utf-8")
    headers = {
        **HTTP_HEADERS_BASE,
        "Authorization": f"Bearer {_clean_key(api_key)}",
    }
    req = urllib.request.Request(
        CEREBRAS_CHAT_URL,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return int(resp.status or 200), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code or 0), exc.read().decode("utf-8", errors="replace")[:800]
    except Exception as exc:
        return 0, str(exc)[:200]


def _content_valid_json(raw_text: str) -> bool:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return False
    choices = parsed.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return False
    content = str((choices[0].get("message") or {}).get("content") or "")
    if not content.strip():
        return False
    try:
        obj = json.loads(content)
        return isinstance(obj, dict)
    except json.JSONDecodeError:
        return content.strip().upper() == "OK"


def _probe_variant(*, api_key: str, variant: str, model: str) -> Dict[str, Any]:
    payload = build_cerebras_payload_variant(variant, model=model)
    status, raw = _cerebras_post(api_key=api_key, payload=payload)
    err_safe = parse_groq_error_safe(raw) if status != 200 else {}
    err_type = classify_http_status(status, err_safe.get("error_type"))
    auth_success = status == 200
    valid_json = _content_valid_json(raw) if auth_success else False
    meta = cerebras_payload_metadata(model=model)
    return {
        "variant": variant,
        "payload_variant": variant,
        "http_status": status or None,
        "auth_success": auth_success,
        "valid_json": valid_json,
        "error_type": None if status == 200 else err_type,
        "error_message_safe": err_safe.get("error_message_safe"),
        "request_id": err_safe.get("request_id"),
        "model": model,
        "payload_mode": meta.get("payload_mode"),
        "base_url": CEREBRAS_CHAT_URL,
    }


def _probe_stage4_style(*, api_key: str, model: str) -> Dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": "You are a JSON API. Respond with a single JSON object only.",
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "final_action": "skip",
                    "symbol": "ETHUSDT",
                    "candidate_side": "NONE",
                    "confidence": 0.0,
                    "why_skip": "probe",
                }
            ),
        },
    ]
    payload = build_stage4_cerebras_openai_payload(model=model, messages=messages, max_tokens=128)
    status, raw = _cerebras_post(api_key=api_key, payload=payload)
    err_safe = parse_groq_error_safe(raw) if status != 200 else {}
    err_type = classify_http_status(status, err_safe.get("error_type"))
    meta = cerebras_payload_metadata(model=model)
    return {
        "variant": "stage4_style_payload",
        "payload_variant": "stage4_style_payload",
        "http_status": status or None,
        "auth_success": status == 200,
        "valid_json": _content_valid_json(raw) if status == 200 else False,
        "error_type": None if status == 200 else err_type,
        "error_message_safe": err_safe.get("error_message_safe"),
        "request_id": err_safe.get("request_id"),
        "model": model,
        "payload_mode": meta.get("payload_mode"),
        "base_url": CEREBRAS_CHAT_URL,
    }


def _infer_root_cause(matrix: List[Dict[str, Any]], root_causes: Dict[str, int]) -> str:
    bare_ok = any(r.get("variant") == "bare_chat_no_response_format" and r.get("auth_success") for r in matrix)
    json_obj_ok = any(r.get("variant") == "json_object_mode" and r.get("auth_success") for r in matrix)
    schema_fail = any(
        str(r.get("variant", "")).startswith("json_schema") and r.get("http_status") == 400 for r in matrix
    )
    stage4_ok = any(r.get("variant") == "stage4_style_payload" and r.get("auth_success") for r in matrix)
    legacy_400 = any(r.get("http_status") == 400 for r in matrix)
    if bare_ok and json_obj_ok and schema_fail:
        return "json_schema_unsupported_use_json_object_mode"
    if not bare_ok and any(r.get("http_status") == 404 for r in matrix):
        return "model_not_found_check_cerebras_model_name"
    if bare_ok and not json_obj_ok:
        return "json_object_mode_rejected_check_prompt_or_model"
    if legacy_400 and not stage4_ok:
        msgs = [r.get("error_message_safe") for r in matrix if r.get("error_message_safe")]
        if msgs and "max_completion_tokens" in str(msgs[0]).lower():
            return "max_completion_tokens_conflict_use_max_tokens_only"
        if msgs:
            return safe_excerpt(str(msgs[0]), 120)
    if stage4_ok:
        return "resolved_stage4_json_object_without_max_completion_tokens"
    if not bare_ok:
        msgs = [r.get("error_message_safe") for r in matrix if r.get("error_message_safe")]
        if msgs:
            return safe_excerpt(str(msgs[0]), 120)
        return "auth_or_network_failure"
    if root_causes:
        top = max(root_causes, key=root_causes.get)
        return f"{top}_see_error_message_safe"
    return "unknown"


def run_payload_matrix(*, model: str = DEFAULT_CEREBRAS_MODEL) -> Dict[str, Any]:
    raw = os.environ.get("CEREBRAS_API_KEY") or ""
    if not raw.strip():
        return {
            "cerebras_matrix_created": True,
            "cerebras_key_present": False,
            "cerebras_key_fingerprint": "",
            "payload_matrix_results": [],
            "any_cerebras_auth_success": False,
            "cerebras_direct_success": False,
            "cerebras_stage4_style_success": False,
            "cerebras_valid_json": False,
            "cerebras_error_root_cause": "missing_api_key",
            "mock_used": False,
            "order_sent": False,
        }

    fp = _fingerprint(_clean_key(raw))
    matrix: List[Dict[str, Any]] = []
    variant_success: Dict[str, int] = {v: 0 for v in PAYLOAD_VARIANTS}
    root_causes: Dict[str, int] = {}

    for variant in PAYLOAD_VARIANTS:
        row = _probe_variant(api_key=raw, variant=variant, model=model)
        row["fingerprint"] = fp
        matrix.append(row)
        if row.get("auth_success"):
            variant_success[variant] = variant_success.get(variant, 0) + 1
        elif row.get("error_type"):
            root_causes[str(row["error_type"])] = root_causes.get(str(row["error_type"]), 0) + 1

    stage4_row = _probe_stage4_style(api_key=raw, model=model)
    stage4_row["fingerprint"] = fp
    matrix.append(stage4_row)
    if stage4_row.get("auth_success"):
        variant_success["stage4_style_payload"] = 1

    any_auth = any(r.get("auth_success") for r in matrix)
    report: Dict[str, Any] = {
        "cerebras_matrix_created": True,
        "cerebras_key_present": True,
        "cerebras_key_fingerprint": fp,
        "payload_matrix_results": matrix,
        "cerebras_payload_matrix_results": matrix,
        "bare_chat_success_count": variant_success.get("bare_chat_no_response_format", 0),
        "json_object_success_count": variant_success.get("json_object_mode", 0),
        "json_schema_strict_false_success_count": variant_success.get("json_schema_strict_false", 0),
        "json_schema_strict_true_success_count": variant_success.get("json_schema_strict_true", 0),
        "stage4_style_success_count": variant_success.get("stage4_style_payload", 0),
        "any_cerebras_auth_success": any_auth,
        "cerebras_direct_success": any_auth,
        "cerebras_stage4_style_success": bool(stage4_row.get("auth_success")),
        "cerebras_valid_json": bool(stage4_row.get("valid_json")),
        "cerebras_error_root_cause": _infer_root_cause(matrix, root_causes),
        **cerebras_payload_metadata(model=model),
        "mock_used": False,
        "order_sent": False,
    }
    serialized = json.dumps(report, ensure_ascii=False)
    report["debug_log_has_api_key"] = _text_has_secret(serialized)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Cerebras auth + payload matrix probe")
    parser.add_argument("--model", default=os.environ.get("STAGE4_CEREBRAS_LLM_MODEL", DEFAULT_CEREBRAS_MODEL))
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    from tools.research.stage4_llm_client import _load_local_env

    _load_local_env()
    model = args.model.strip()
    report = run_payload_matrix(model=model)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report["report_path"] = str(out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = bool(report.get("cerebras_stage4_style_success") or report.get("cerebras_direct_success"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
