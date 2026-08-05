"""Redaction helpers for residual sensitive string values."""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

_REDACT_KEY_FRAGMENTS: tuple[str, ...] = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "authorization",
    "cookie",
    "wallet",
    "account",
)

_SECRET_BLOB_RE = re.compile(
    r"(?i)(sk-[a-z0-9]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"bearer\s+[a-z0-9\-._~+/]+=*)"
)


def _key_needs_redaction(key: str) -> bool:
    low = str(key).lower().replace("-", "_")
    return any(frag in low for frag in _REDACT_KEY_FRAGMENTS)


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        if _SECRET_BLOB_RE.search(value):
            return REDACTED
        return value
    return value


def redact_payload(payload: Any) -> Any:
    """Deep redact by key fragment and secret-shaped string values."""
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if _key_needs_redaction(str(k)):
                out[k] = REDACTED
            else:
                out[k] = redact_payload(v)
        return out
    if isinstance(payload, list):
        return [redact_payload(x) for x in payload]
    return redact_value(payload)
