"""Cerebras OpenAI-compat payload helpers (Stage 4 diagnostics + client)."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from tools.research.stage4_groq_payload import (
    JSON_SCHEMA_BODY,
    classify_http_status,
    parse_groq_error_safe,
)

CEREBRAS_CHAT_URL = "https://api.cerebras.ai/v1/chat/completions"
DEFAULT_CEREBRAS_MODEL = "gpt-oss-120b"

PAYLOAD_VARIANTS = (
    "bare_chat_no_response_format",
    "json_object_mode",
    "json_schema_strict_false",
    "json_schema_strict_true",
)


STAGE4_DECISION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "final_action": {"type": "string"},
        "decision_intent": {"type": "string"},
        "symbol": {"type": "string"},
        "candidate_side": {"type": "string"},
        "confidence": {"type": "number"},
        "why_enter": {"type": "string"},
        "why_skip": {"type": "string"},
        "side_reason": {"type": "string"},
        "confidence_reason": {"type": "string"},
        "risk_notes": {"type": "array"},
        "patch_awareness": {"type": "string"},
        "uncertainty": {"type": "string"},
        "requires_manual_review": {"type": "boolean"},
    },
    "required": [
        "final_action",
        "symbol",
        "candidate_side",
        "confidence",
        "why_enter",
        "why_skip",
        "side_reason",
        "confidence_reason",
        "risk_notes",
        "patch_awareness",
        "uncertainty",
        "requires_manual_review",
    ],
    "additionalProperties": True,
}


def resolve_cerebras_max_tokens() -> int:
    raw = os.environ.get("STAGE4_CEREBRAS_MAX_TOKENS", "1100").strip()
    try:
        return max(128, int(float(raw)))
    except (TypeError, ValueError):
        return 1100


def resolve_cerebras_retry_max_tokens() -> int:
    raw = os.environ.get("STAGE4_CEREBRAS_RETRY_MAX_TOKENS", "1400").strip()
    try:
        return max(128, int(float(raw)))
    except (TypeError, ValueError):
        return 1400


CEREBRAS_TRUNCATION_RETRY_INSTRUCTION = (
    "Re-output ONLY valid compact JSON matching the schema. "
    "Keep why_enter, why_skip, side_reason, confidence_reason, and patch_awareness under 80 characters each. "
    "No markdown or prose outside JSON."
)


def compact_cerebras_retry_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Shorter output instruction for a single safe Cerebras truncation retry."""
    out: List[Dict[str, str]] = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        content = str(msg.get("content") or "").rstrip()
        if role in {"system", "user"}:
            content = f"{content}\n\n{CEREBRAS_TRUNCATION_RETRY_INSTRUCTION}"
        out.append({"role": role, "content": content})
    return out


def resolve_cerebras_payload_mode() -> str:
    mode = os.environ.get("STAGE4_CEREBRAS_PAYLOAD_MODE", "json_schema").strip().lower()
    return mode if mode in {"json_object", "json_schema"} else "json_schema"


def cerebras_payload_metadata(*, model: str = DEFAULT_CEREBRAS_MODEL) -> Dict[str, Any]:
    mode = resolve_cerebras_payload_mode()
    return {
        "payload_mode": mode,
        "json_schema_used": mode == "json_schema",
        "strict_schema_used": False,
        "model": model,
        "base_url": CEREBRAS_CHAT_URL,
        "max_tokens": resolve_cerebras_max_tokens(),
    }


def build_cerebras_payload_variant(variant: str, *, model: str = DEFAULT_CEREBRAS_MODEL) -> Dict[str, Any]:
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


def build_stage4_cerebras_openai_payload(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float = 0.2,
    payload_mode: str | None = None,
) -> Dict[str, Any]:
    """Stage4 Cerebras payload: json_object or json_schema; max_tokens only."""
    mode = payload_mode or resolve_cerebras_payload_mode()
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if mode == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "stage4_decision",
                "strict": False,
                "schema": STAGE4_DECISION_JSON_SCHEMA,
            },
        }
    else:
        payload["response_format"] = {"type": "json_object"}
    return payload


def build_stage4_cerebras_probe_payload(
    *,
    model: str,
    max_tokens: int,
    payload_mode: str,
) -> Dict[str, Any]:
    """Minimal Stage4-style decision probe payload (short context)."""
    user_content = json.dumps(
        {
            "task": "stage4_dry_run_decision",
            "symbol": "ETHUSDT",
            "market_context": {
                "regime": "range",
                "trend_15m": "flat",
                "change_24h_pct": 0.1,
            },
            "instructions": "Return one JSON decision object only.",
        },
        ensure_ascii=False,
    )
    messages = [
        {
            "role": "system",
            "content": "Respond with one JSON object matching the Stage4 decision schema.",
        },
        {"role": "user", "content": user_content},
    ]
    return build_stage4_cerebras_openai_payload(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0,
        payload_mode=payload_mode,
    )


def build_stage4_cerebras_legacy_payload(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """Legacy Stage4 payload shape (both max_tokens and max_completion_tokens)."""
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }


def classify_cerebras_http_error(*, http_status: int, body: str) -> str:
    """Map Cerebras HTTP/body errors; keep empty vs quota distinct from truncation."""
    err_safe = parse_groq_error_safe(body)
    err_type = str(err_safe.get("error_type") or "").lower()
    msg = str(err_safe.get("error_message_safe") or body or "").lower()
    if http_status == 429 or "quota" in msg or "rate limit" in msg or err_type == "rate_limit":
        return "provider_quota_exhausted"
    if http_status in {401, 403}:
        return "http_forbidden" if http_status == 403 else "http_unauthorized"
    if http_status >= 500:
        return "server_error"
    return err_type or f"http_{http_status}"


__all__ = [
    "CEREBRAS_CHAT_URL",
    "DEFAULT_CEREBRAS_MODEL",
    "PAYLOAD_VARIANTS",
    "STAGE4_DECISION_JSON_SCHEMA",
    "build_cerebras_payload_variant",
    "build_stage4_cerebras_legacy_payload",
    "build_stage4_cerebras_openai_payload",
    "build_stage4_cerebras_probe_payload",
    "cerebras_payload_metadata",
    "classify_cerebras_http_error",
    "classify_http_status",
    "parse_groq_error_safe",
    "resolve_cerebras_max_tokens",
    "resolve_cerebras_retry_max_tokens",
    "resolve_cerebras_payload_mode",
    "compact_cerebras_retry_messages",
    "CEREBRAS_TRUNCATION_RETRY_INSTRUCTION",
]
