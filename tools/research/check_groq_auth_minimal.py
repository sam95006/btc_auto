#!/usr/bin/env python3
"""Minimal Groq auth + payload matrix probe — direct HTTP, no secrets in output."""
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

from tools.research.stage4_groq_payload import (  # noqa: E402
    DEFAULT_GROQ_MODEL,
    GROQ_CHAT_URL,
    PAYLOAD_VARIANTS,
    build_groq_payload_variant,
    build_stage4_groq_openai_payload,
    classify_http_status,
    groq_payload_metadata,
    parse_groq_error_safe,
)
from tools.research.stage4_response_parser import safe_excerpt  # noqa: E402

GROQ_ENV_NAMES = ("GROQ_API_KEY_PRIMARY", "GROQ_API_KEY_SECONDARY", "GROQ_API_KEY")

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


def _groq_post(*, api_key: str, payload: Dict[str, Any]) -> Tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GROQ_CHAT_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {_clean_key(api_key)}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
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
    payload = build_groq_payload_variant(variant, model=model)
    status, raw = _groq_post(api_key=api_key, payload=payload)
    err_safe = parse_groq_error_safe(raw) if status != 200 else {}
    err_type = classify_http_status(status, err_safe.get("error_type"))
    auth_success = status == 200
    valid_json = _content_valid_json(raw) if auth_success else False
    return {
        "payload_variant": variant,
        "http_status": status or None,
        "auth_success": auth_success,
        "valid_json": valid_json,
        "error_type": None if status == 200 else err_type,
        "error_message_safe": err_safe.get("error_message_safe"),
        "request_id": err_safe.get("request_id"),
        "model": model,
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
    payload = build_stage4_groq_openai_payload(model=model, messages=messages, max_tokens=128)
    status, raw = _groq_post(api_key=api_key, payload=payload)
    err_safe = parse_groq_error_safe(raw) if status != 200 else {}
    err_type = classify_http_status(status, err_safe.get("error_type"))
    return {
        "payload_variant": "stage4_json_object_no_max_completion_tokens",
        "http_status": status or None,
        "auth_success": status == 200,
        "valid_json": _content_valid_json(raw) if status == 200 else False,
        "error_type": None if status == 200 else err_type,
        "error_message_safe": err_safe.get("error_message_safe"),
        "request_id": err_safe.get("request_id"),
        "model": model,
        **groq_payload_metadata(model=model),
    }


def run_payload_matrix(*, model: str = DEFAULT_GROQ_MODEL, include_legacy: bool = False) -> Dict[str, Any]:
    names = [n for n in GROQ_ENV_NAMES if n != "GROQ_API_KEY" or include_legacy]
    matrix: List[Dict[str, Any]] = []
    seen: set[str] = set()
    variant_success: Dict[str, int] = {v: 0 for v in PAYLOAD_VARIANTS}
    root_causes: Dict[str, int] = {}

    for env_name in names:
        raw = os.environ.get(env_name) or ""
        if not raw.strip():
            continue
        fp = _fingerprint(_clean_key(raw))
        if fp in seen:
            continue
        seen.add(fp)
        for variant in PAYLOAD_VARIANTS:
            row = _probe_variant(api_key=raw, variant=variant, model=model)
            row["env_name"] = env_name
            row["fingerprint"] = fp
            matrix.append(row)
            if row.get("auth_success"):
                variant_success[variant] = variant_success.get(variant, 0) + 1
            elif row.get("error_type"):
                root_causes[str(row["error_type"])] = root_causes.get(str(row["error_type"]), 0) + 1

        stage4_row = _probe_stage4_style(api_key=raw, model=model)
        stage4_row["env_name"] = env_name
        stage4_row["fingerprint"] = fp
        matrix.append(stage4_row)
        if stage4_row.get("auth_success"):
            variant_success["stage4_json_object_no_max_completion_tokens"] = (
                variant_success.get("stage4_json_object_no_max_completion_tokens", 0) + 1
            )

    any_auth = any(r.get("auth_success") for r in matrix)
    report: Dict[str, Any] = {
        "groq_dashboard_observation_considered": True,
        "groq_key_count": len(seen),
        "groq_key_fingerprints": sorted(seen),
        "payload_matrix_created": True,
        "payload_matrix_results": matrix,
        "bare_chat_success_count": variant_success.get("bare_chat_no_response_format", 0),
        "json_object_success_count": variant_success.get("json_object_mode", 0),
        "json_schema_strict_false_success_count": variant_success.get("json_schema_strict_false", 0),
        "json_schema_strict_true_success_count": variant_success.get("json_schema_strict_true", 0),
        "stage4_style_success_count": variant_success.get("stage4_json_object_no_max_completion_tokens", 0),
        "any_groq_auth_success": any_auth,
        "groq_400_root_cause": _infer_root_cause(matrix, root_causes),
        **groq_payload_metadata(model=model),
        "mock_used": False,
        "order_sent": False,
    }
    serialized = json.dumps(report, ensure_ascii=False)
    report["debug_log_has_api_key"] = _text_has_secret(serialized)
    return report


def _infer_root_cause(matrix: List[Dict[str, Any]], root_causes: Dict[str, int]) -> str:
    bare_ok = any(
        r.get("payload_variant") == "bare_chat_no_response_format" and r.get("auth_success") for r in matrix
    )
    json_obj_ok = any(r.get("payload_variant") == "json_object_mode" and r.get("auth_success") for r in matrix)
    schema_fail = any(
        r.get("payload_variant", "").startswith("json_schema") and r.get("http_status") == 400 for r in matrix
    )
    stage4_ok = any(r.get("payload_variant") == "stage4_json_object_no_max_completion_tokens" and r.get("auth_success") for r in matrix)
    if bare_ok and json_obj_ok and schema_fail:
        return "json_schema_unsupported_use_json_object_mode"
    if bare_ok and not json_obj_ok:
        return "json_object_mode_rejected_check_prompt_or_model"
    if not bare_ok:
        msgs = [r.get("error_message_safe") for r in matrix if r.get("error_message_safe")]
        if msgs:
            return safe_excerpt(str(msgs[0]), 120)
        return "auth_or_network_failure"
    if stage4_ok:
        return "resolved_stage4_json_object_without_max_completion_tokens"
    if root_causes:
        top = max(root_causes, key=root_causes.get)
        return f"{top}_see_error_message_safe"
    return "unknown"


def run_minimal_groq_auth(*, model: str = DEFAULT_GROQ_MODEL, include_legacy: bool = False) -> Dict[str, Any]:
    matrix = run_payload_matrix(model=model, include_legacy=include_legacy)
    matrix["probe_mode"] = "minimal_json_object"
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description="Groq auth + payload matrix probe")
    parser.add_argument("--model", default=os.environ.get("STAGE4_LLM_MODEL", DEFAULT_GROQ_MODEL))
    parser.add_argument("--output", default="", help="Optional JSON output path")
    parser.add_argument("--include-legacy", action="store_true")
    parser.add_argument("--matrix", action="store_true", help="Run A/B/C/D payload matrix")
    args = parser.parse_args()

    from tools.research.stage4_llm_client import _load_local_env

    _load_local_env()
    model = args.model.strip()
    report = run_payload_matrix(model=model, include_legacy=args.include_legacy) if args.matrix else run_minimal_groq_auth(
        model=model, include_legacy=args.include_legacy
    )
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report["report_path"] = str(out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = bool(report.get("any_groq_auth_success"))
    if args.matrix:
        ok = ok and int(report.get("json_object_success_count") or 0) >= 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
