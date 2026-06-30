"""Cerebras OpenAI-compat payload helpers (Stage 4 diagnostics + client)."""
from __future__ import annotations

import json
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


def cerebras_payload_metadata(*, model: str = DEFAULT_CEREBRAS_MODEL) -> Dict[str, Any]:
    return {
        "payload_mode": "json_object",
        "json_schema_used": False,
        "strict_schema_used": False,
        "model": model,
        "base_url": CEREBRAS_CHAT_URL,
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
) -> Dict[str, Any]:
    """Stage4 Cerebras payload: json_object, max_tokens only (no max_completion_tokens)."""
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }


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


__all__ = [
    "CEREBRAS_CHAT_URL",
    "DEFAULT_CEREBRAS_MODEL",
    "PAYLOAD_VARIANTS",
    "build_cerebras_payload_variant",
    "build_stage4_cerebras_legacy_payload",
    "build_stage4_cerebras_openai_payload",
    "cerebras_payload_metadata",
    "classify_http_status",
    "parse_groq_error_safe",
]
