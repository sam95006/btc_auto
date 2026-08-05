"""Sanitize / assert Founder-private observability payloads never leak secrets."""
from __future__ import annotations

import json
from typing import Any

from backend.nexus_observability.constants import FORBIDDEN_OBSERVABILITY_KEYS


def _walk_keys(obj: Any, *, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            path = f"{prefix}.{key}" if prefix else key
            if key.lower() in FORBIDDEN_OBSERVABILITY_KEYS:
                found.append(path)
            found.extend(_walk_keys(v, prefix=path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(_walk_keys(item, prefix=f"{prefix}[{i}]"))
    return found


def assert_no_forbidden_keys(payload: dict[str, Any]) -> None:
    leaked = _walk_keys(payload)
    if leaked:
        raise RuntimeError(f"observability_secret_keys:{leaked}")


def redact_forbidden_keys(payload: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy dict replacing forbidden key values with [REDACTED]."""

    def _clean(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if str(k).lower() in FORBIDDEN_OBSERVABILITY_KEYS:
                    out[str(k)] = "[REDACTED]"
                else:
                    out[str(k)] = _clean(v)
            return out
        if isinstance(obj, list):
            return [_clean(x) for x in obj]
        return obj

    return _clean(payload)


def payload_contains_secret_pattern(payload: Any) -> bool:
    blob = json.dumps(payload, default=str).lower()
    markers = (
        "begin rsa private key",
        "begin openssh private key",
        "sk-",
        "bybit_api_key=",
        "bybit_api_secret=",
    )
    return any(m in blob for m in markers)
