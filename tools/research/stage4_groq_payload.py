"""Groq OpenAI-compat payload helpers and safe error parsing."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from tools.research.stage4_response_parser import safe_excerpt

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

JSON_SCHEMA_BODY = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "decision": {"type": "string"},
    },
    "required": ["ok", "decision"],
    "additionalProperties": False,
}

SECRET_IN_ERROR = re.compile(r"gsk_[A-Za-z0-9]{10,}")


def groq_payload_metadata(*, model: str = DEFAULT_GROQ_MODEL) -> Dict[str, Any]:
    return {
        "groq_payload_mode": "json_object",
        "json_schema_used": False,
        "strict_schema_used": False,
        "model": model,
        "base_url": GROQ_CHAT_URL,
    }


def parse_groq_error_safe(raw_text: str) -> Dict[str, Any]:
    """Extract safe Groq error fields without secrets or full prompts."""
    text = (raw_text or "").strip()
    if SECRET_IN_ERROR.search(text):
        text = SECRET_IN_ERROR.sub("[redacted]", text)
    out: Dict[str, Any] = {
        "error_type": None,
        "error_message_safe": None,
        "request_id": None,
    }
    if not text:
        return out
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        out["error_message_safe"] = safe_excerpt(text, 200)
        return out
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        out["error_type"] = str(err.get("type") or "") or None
        msg = str(err.get("message") or "")
        if SECRET_IN_ERROR.search(msg):
            msg = SECRET_IN_ERROR.sub("[redacted]", msg)
        out["error_message_safe"] = safe_excerpt(msg, 200) or None
    else:
        out["error_message_safe"] = safe_excerpt(text, 200)
    req_id = body.get("request_id") if isinstance(body, dict) else None
    if not req_id and isinstance(err, dict):
        req_id = err.get("request_id")
    out["request_id"] = str(req_id) if req_id else None
    return out


def build_groq_payload_variant(variant: str, *, model: str = DEFAULT_GROQ_MODEL) -> Dict[str, Any]:
    if variant == "bare_chat_no_response_format":
        return {
            "model": model,
            "messages": [{"role": "user", "content": "Return exactly: OK"}],
            "temperature": 0,
            "max_tokens": 16,
        }
    if variant == "json_object_mode":
        return {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a JSON API. Respond only with valid JSON.",
                },
                {
                    "role": "user",
                    "content": 'Return {"ok": true, "decision": "skip"}',
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 128,
        }
    if variant in {"json_schema_strict_false", "json_schema_strict_true"}:
        strict = variant == "json_schema_strict_true"
        return {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a JSON API. Respond only with valid JSON matching the schema.",
                },
                {
                    "role": "user",
                    "content": 'Return {"ok": true, "decision": "skip"}',
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "minimal_decision",
                    "strict": strict,
                    "schema": JSON_SCHEMA_BODY,
                },
            },
            "temperature": 0,
            "max_tokens": 128,
        }
    raise ValueError(f"unknown variant: {variant}")


PAYLOAD_VARIANTS: Tuple[str, ...] = (
    "bare_chat_no_response_format",
    "json_object_mode",
    "json_schema_strict_false",
    "json_schema_strict_true",
)


def build_stage4_groq_openai_payload(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """Stage4 Groq payload: json_object mode, max_tokens only (no max_completion_tokens)."""
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }


def classify_http_status(status: int, error_type: str | None = None) -> str:
    if status == 200:
        return "ok"
    if error_type:
        return error_type
    if status == 401:
        return "http_unauthorized"
    if status == 403:
        return "http_forbidden"
    if status == 429:
        return "rate_limit"
    if status == 400:
        return "invalid_request_error"
    return f"http_{status}"
