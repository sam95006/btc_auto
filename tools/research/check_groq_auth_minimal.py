#!/usr/bin/env python3
"""Minimal Groq auth probe — direct HTTP, no Stage4 wrapper, no secrets in output."""
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

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
GROQ_ENV_NAMES = ("GROQ_API_KEY_PRIMARY", "GROQ_API_KEY_SECONDARY", "GROQ_API_KEY")

SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
)


def _fingerprint(key: str) -> str:
    if not key:
        return ""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _text_has_secret(text: str) -> bool:
    return any(pat.search(text) for pat in SECRET_PATTERNS)


def _inspect_key_format(raw: str) -> Dict[str, Any]:
    """Key hygiene checks without printing the key."""
    if not raw:
        return {
            "present": False,
            "has_leading_or_trailing_whitespace": False,
            "has_quote_wrapping": False,
            "has_newline": False,
            "key_format_looks_valid": False,
        }
    stripped = raw.strip()
    has_ws = raw != stripped or raw.startswith(" ") or raw.endswith(" ")
    has_quotes = (
        (raw.startswith('"') and raw.endswith('"'))
        or (raw.startswith("'") and raw.endswith("'"))
        or (stripped.startswith('"') and stripped.endswith('"'))
        or (stripped.startswith("'") and stripped.endswith("'"))
    )
    has_newline = "\n" in raw or "\r" in raw
    inner = stripped.strip('"').strip("'")
    looks_valid = bool(re.fullmatch(r"gsk_[A-Za-z0-9_-]{20,}", inner))
    return {
        "present": True,
        "has_leading_or_trailing_whitespace": has_ws,
        "has_quote_wrapping": has_quotes,
        "has_newline": has_newline,
        "key_format_looks_valid": looks_valid,
    }


def _http_error_type(code: int) -> str:
    if code == 401:
        return "http_unauthorized"
    if code == 403:
        return "http_forbidden"
    if code == 429:
        return "rate_limit"
    if code == 404:
        return "http_not_found"
    if code >= 500:
        return "server_error"
    return f"http_{code}"


def _minimal_chat_request(*, api_key: str, model: str) -> Tuple[int, Dict[str, Any], str]:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": 'Return one JSON object only: {"status":"ok","probe":"groq_minimal_auth"}',
            }
        ],
        "temperature": 0,
        "max_tokens": 64,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload).encode("utf-8")
    key_clean = api_key.strip().strip('"').strip("'")
    req = urllib.request.Request(
        GROQ_CHAT_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key_clean}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = int(resp.status or 200)
            raw_text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = int(exc.code or 0)
        raw_text = exc.read().decode("utf-8", errors="replace")[:500]
        return status, {}, raw_text
    except Exception as exc:
        return 0, {}, str(exc)[:200]

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return status, {}, raw_text

    content = ""
    choices = parsed.get("choices") or []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        content = str(msg.get("content") or "")
    valid_json = False
    if content.strip():
        try:
            obj = json.loads(content)
            valid_json = isinstance(obj, dict)
        except json.JSONDecodeError:
            valid_json = False
    return status, {"valid_json": valid_json, "raw_content_length": len(content)}, raw_text[:200]


def run_minimal_groq_auth(
    *,
    env_names: Tuple[str, ...] | None = None,
    model: str = DEFAULT_MODEL,
    include_legacy: bool = False,
) -> Dict[str, Any]:
    names = list(env_names or GROQ_ENV_NAMES)
    if not include_legacy:
        names = [n for n in names if n != "GROQ_API_KEY"]

    results: List[Dict[str, Any]] = []
    format_valid_count = 0
    whitespace_issues = 0
    quote_issues = 0
    http_distribution: Dict[str, int] = {}

    seen_fps: set[str] = set()
    for env_name in names:
        raw = os.environ.get(env_name) or ""
        fmt = _inspect_key_format(raw)
        if not fmt.get("present"):
            continue
        inner = raw.strip().strip('"').strip("'")
        fp = _fingerprint(inner)
        if fp in seen_fps:
            continue
        seen_fps.add(fp)

        if fmt.get("key_format_looks_valid"):
            format_valid_count += 1
        if fmt.get("has_leading_or_trailing_whitespace") or fmt.get("has_newline"):
            whitespace_issues += 1
        if fmt.get("has_quote_wrapping"):
            quote_issues += 1

        status, meta, _ = _minimal_chat_request(api_key=inner, model=model)
        err_type = None if status == 200 else _http_error_type(status)
        if err_type:
            http_distribution[err_type] = http_distribution.get(err_type, 0) + 1
        elif status == 200:
            http_distribution["http_200"] = http_distribution.get("http_200", 0) + 1

        auth_success = status == 200
        valid_json = bool(meta.get("valid_json")) if auth_success else False
        results.append(
            {
                "env_name": env_name,
                "fingerprint": fp,
                "http_status": status or None,
                "auth_success": auth_success,
                "valid_json": valid_json,
                "error_type": err_type,
                "has_leading_or_trailing_whitespace": fmt.get("has_leading_or_trailing_whitespace"),
                "has_quote_wrapping": fmt.get("has_quote_wrapping"),
                "has_newline": fmt.get("has_newline"),
                "key_format_looks_valid": fmt.get("key_format_looks_valid"),
                "authorization_scheme": "Bearer",
                "base_url": GROQ_CHAT_URL,
                "model": model,
            }
        )

    any_success = any(r.get("auth_success") for r in results)
    report: Dict[str, Any] = {
        "groq_key_count": len(results),
        "groq_key_fingerprints": [r.get("fingerprint") for r in results],
        "groq_key_format_valid_count": format_valid_count,
        "groq_key_has_whitespace_issue": whitespace_issues > 0,
        "groq_key_has_quote_issue": quote_issues > 0,
        "results": results,
        "any_groq_auth_success": any_success,
        "groq_minimal_http_status_distribution": http_distribution,
        "mock_used": False,
        "order_sent": False,
    }
    serialized = json.dumps(report, ensure_ascii=False)
    report["debug_log_has_api_key"] = _text_has_secret(serialized)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal Groq auth probe (no secrets logged)")
    parser.add_argument("--model", default=os.environ.get("STAGE4_LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--output", default="", help="Optional JSON output path")
    parser.add_argument("--include-legacy", action="store_true", help="Include GROQ_API_KEY env")
    args = parser.parse_args()

    from tools.research.stage4_llm_client import _load_local_env

    _load_local_env()
    report = run_minimal_groq_auth(model=args.model.strip(), include_legacy=args.include_legacy)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report["report_path"] = str(out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("any_groq_auth_success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
