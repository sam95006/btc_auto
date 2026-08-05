"""Payload sanitization for Public Decision Cloud."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_decision_cloud.constants import FORBIDDEN_PAYLOAD_KEYS


class ForbiddenPayloadKeyError(ValueError):
    """Raised when a banned key appears in a Decision Cloud payload."""


_EXTRA_BANNED_FRAGMENTS = (
    "api_key",
    "api_secret",
    "private_key",
    "strategy_weight",
    "system_prompt",
    "provider_prompt",
    "provider_response",
)

# Exact private lesson / prompt keys (not public attestation booleans).
_EXACT_PRIVATE_KEYS = frozenset(
    {
        "lesson_memory",
        "lesson_id",
        "lesson_ids",
        "private_lesson_id",
        "lesson_memory_private",
        "raw_provider_prompt",
        "raw_provider_response",
        "system_prompt",
        "prompt",
        "prompts",
    }
)

# Public attestation keys allowed only when False / absent of secret material.
_ATTESTATION_BOOL_KEYS = frozenset({"private_lesson_memory"})


def _is_forbidden_key(key: str, value: Any = None) -> bool:
    key_l = str(key).lower()
    if key_l in _ATTESTATION_BOOL_KEYS:
        # Attestation must be explicitly False — True would claim private memory exposure.
        return value is not False
    if key_l in FORBIDDEN_PAYLOAD_KEYS or key_l in _EXACT_PRIVATE_KEYS:
        return True
    return any(banned in key_l for banned in _EXTRA_BANNED_FRAGMENTS)


def assert_no_forbidden_keys(obj: Any, *, path: str = "$") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if _is_forbidden_key(str(key), value):
                raise ForbiddenPayloadKeyError(f"forbidden key at {path}.{key}")
            assert_no_forbidden_keys(value, path=f"{path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            assert_no_forbidden_keys(item, path=f"{path}[{i}]")


def scrub_forbidden_keys(obj: Any) -> Any:
    """Drop forbidden keys rather than failing — used for fixture defense-in-depth."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if _is_forbidden_key(str(key), value):
                continue
            out[key] = scrub_forbidden_keys(value)
        return out
    if isinstance(obj, list):
        return [scrub_forbidden_keys(x) for x in obj]
    return obj
