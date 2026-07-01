#!/usr/bin/env python3
"""Stage4-style Cerebras decision probe — variants A-D, no orders, no secrets in output."""
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
    build_stage4_cerebras_probe_payload,
    parse_groq_error_safe,
)
from tools.research.stage4_decision_schema import parse_llm_decision  # noqa: E402
from tools.research.stage4_response_parser import extract_openai_compat_content
from tools.research.stage4_response_parser import safe_excerpt  # noqa: E402

SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),
    re.compile(r"csk-[A-Za-z0-9]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
)

PROBE_VARIANTS = (
    ("A", "json_object", 500),
    ("B", "json_object", 900),
    ("C", "json_schema", 500),
    ("D", "json_schema", 900),
)


def _fingerprint(key: str) -> str:
    if not key:
        return ""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _text_has_secret(text: str) -> bool:
    return any(pat.search(text) for pat in SECRET_PATTERNS)


def _clean_key(raw: str) -> str:
    return raw.strip().strip('"').strip("'")


def _post(*, api_key: str, payload: Dict[str, Any]) -> Tuple[int, str]:
    from tools.research.stage4_llm_client import HTTP_HEADERS_BASE

    body = json.dumps(payload).encode("utf-8")
    headers = {**HTTP_HEADERS_BASE, "Authorization": f"Bearer {_clean_key(api_key)}"}
    req = urllib.request.Request(CEREBRAS_CHAT_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return int(resp.status or 200), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code or 0), exc.read().decode("utf-8", errors="replace")[:800]
    except Exception as exc:
        return 0, str(exc)[:200]


def _classify_row(*, http_status: int, content: str, finish_reason: str | None, valid_json: bool) -> str:
    if http_status == 429:
        return "provider_quota_exhausted"
    if http_status == 200 and not content.strip():
        return "provider_empty_response"
    if not valid_json and str(finish_reason or "").lower() == "length":
        return "provider_response_truncated"
    if not valid_json:
        return "json_decode_error"
    return ""


def run_variant(
    *,
    api_key: str,
    model: str,
    variant: str,
    payload_mode: str,
    max_tokens: int,
) -> Dict[str, Any]:
    payload = build_stage4_cerebras_probe_payload(
        model=model,
        max_tokens=max_tokens,
        payload_mode=payload_mode,
    )
    http_status, raw_body = _post(api_key=api_key, payload=payload)
    err_safe = parse_groq_error_safe(raw_body)
    content = ""
    finish_reason = None
    if http_status == 200:
        try:
            parsed_body = json.loads(raw_body)
            content, _, finish_reason = extract_openai_compat_content(parsed_body)
        except json.JSONDecodeError:
            content = ""
    parsed_decision: Dict[str, Any] = {}
    schema_ok = False
    if content.strip():
        try:
            parsed_decision = json.loads(content)
            _, schema_ok, _ = parse_llm_decision(parsed_decision, symbol="ETHUSDT")
        except json.JSONDecodeError:
            schema_ok = False
    valid_json = http_status == 200 and bool(content.strip()) and schema_ok
    error_type = _classify_row(
        http_status=http_status,
        content=content,
        finish_reason=finish_reason,
        valid_json=valid_json,
    )
    if http_status != 200 and not error_type:
        from tools.research.stage4_cerebras_payload import classify_cerebras_http_error

        error_type = classify_cerebras_http_error(http_status=http_status, body=raw_body)
    return {
        "variant": variant,
        "payload_mode": payload_mode,
        "max_tokens": max_tokens,
        "http_status": http_status,
        "valid_json": valid_json,
        "finish_reason": finish_reason,
        "response_text_chars": len(content or ""),
        "error_type": error_type or None,
        "error_message_safe": err_safe.get("error_message_safe"),
        "cerebras_stage4_decision_valid_json": valid_json,
        "mock_used": False,
        "order_sent": False,
    }


def run_probe_matrix(*, model: str | None = None, variants: List[Tuple[str, str, int]] | None = None) -> Dict[str, Any]:
    model_name = (model or os.environ.get("STAGE4_CEREBRAS_LLM_MODEL") or DEFAULT_CEREBRAS_MODEL).strip()
    api_key = (os.environ.get("CEREBRAS_API_KEY") or "").strip()
    rows: List[Dict[str, Any]] = []
    if not api_key:
        return {
            "cerebras_key_present": False,
            "cerebras_stage4_decision_valid_json": False,
            "variants": [],
            "best_variant": None,
            "probe_call_count": 0,
            "mock_used": False,
            "order_sent": False,
            "error_type": "missing_api_key",
        }
    chosen = variants or list(PROBE_VARIANTS)
    for label, mode, tokens in chosen:
        rows.append(
            run_variant(
                api_key=api_key,
                model=model_name,
                variant=label,
                payload_mode=mode,
                max_tokens=tokens,
            )
        )
    best = next((r for r in rows if r.get("valid_json") and str(r.get("finish_reason") or "").lower() != "length"), None)
    if best is None:
        best = next((r for r in rows if r.get("valid_json")), None)
    serialized = json.dumps(rows, ensure_ascii=False)
    return {
        "cerebras_key_present": True,
        "cerebras_key_fingerprint": _fingerprint(_clean_key(api_key)),
        "cerebras_model": model_name,
        "cerebras_stage4_decision_valid_json": bool(best),
        "variants": rows,
        "best_variant": best.get("variant") if best else None,
        "best_payload_mode": best.get("payload_mode") if best else None,
        "best_max_tokens": best.get("max_tokens") if best else None,
        "probe_call_count": len(rows),
        "mock_used": False,
        "order_sent": False,
        "debug_log_has_api_key": _text_has_secret(serialized),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage4 Cerebras decision probe (A-D variants)")
    parser.add_argument("--model", default="", help="Cerebras model override")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()
    from tools.research.stage4_llm_client import _load_local_env

    _load_local_env()
    report = run_probe_matrix(model=args.model or None)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report["output_path"] = str(out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("cerebras_stage4_decision_valid_json") else 1


if __name__ == "__main__":
    raise SystemExit(main())
