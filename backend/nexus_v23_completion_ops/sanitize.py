"""Sanitize V13-B completion ops payloads — never log or emit secrets."""
from __future__ import annotations

import json
import re
from typing import Any

from backend.nexus_v23_completion_ops.constants import FORBIDDEN_LOG_KEYS

_SECRET_BLOB_MARKERS = (
    "begin rsa private key",
    "begin openssh private key",
    "sk-",
    "bybit_api_key=",
    "bybit_api_secret=",
    "authorization: bearer",
)


def _walk_forbidden_keys(obj: Any, *, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            path = f"{prefix}.{key}" if prefix else key
            if key.lower() in FORBIDDEN_LOG_KEYS:
                found.append(path)
            found.extend(_walk_forbidden_keys(v, prefix=path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(_walk_forbidden_keys(item, prefix=f"{prefix}[{i}]"))
    return found


def assert_no_secret_keys(payload: dict[str, Any]) -> None:
    leaked = _walk_forbidden_keys(payload)
    if leaked:
        raise RuntimeError(f"v23_completion_ops_secret_keys:{leaked}")


def strip_forbidden_keys(payload: Any) -> Any:
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if str(k).lower() in FORBIDDEN_LOG_KEYS:
                continue
            out[str(k)] = strip_forbidden_keys(v)
        return out
    if isinstance(payload, list):
        return [strip_forbidden_keys(x) for x in payload]
    return payload


def safe_log_fields(event: dict[str, Any]) -> dict[str, Any]:
    cleaned = strip_forbidden_keys(event)
    headers = cleaned.get("headers") if isinstance(cleaned, dict) else None
    if isinstance(headers, dict):
        cleaned["headers"] = {
            str(k): v
            for k, v in headers.items()
            if str(k).lower() not in {"authorization", "x-api-key"} | FORBIDDEN_LOG_KEYS
        }
    assert_no_secret_keys(cleaned if isinstance(cleaned, dict) else {"value": cleaned})
    return cleaned if isinstance(cleaned, dict) else {"value": cleaned}


def payload_contains_secret_pattern(payload: Any) -> bool:
    blob = json.dumps(payload, default=str).lower()
    return any(m in blob for m in _SECRET_BLOB_MARKERS)


_SECRET_FILE_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]


def secret_patterns() -> list[re.Pattern[str]]:
    return list(_SECRET_FILE_PATTERNS)
