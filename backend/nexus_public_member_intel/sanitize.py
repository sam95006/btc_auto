"""Sanitize / forbidden-key enforcement for Member Web Intelligence."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_member_intel.constants import FORBIDDEN_PAYLOAD_KEYS


class ForbiddenPayloadKeyError(ValueError):
    """Raised when a banned key appears in a member intel payload."""


_EXTRA_BANNED_FRAGMENTS = (
    "api_key",
    "api_secret",
    "private_key",
    "strategy_weight",
    "system_prompt",
    "provider_prompt",
    "guarantee_pct",
    "win_rate_guarantee",
)


def _is_forbidden_key(key: str) -> bool:
    key_l = str(key).lower()
    if key_l in FORBIDDEN_PAYLOAD_KEYS:
        return True
    # Attestation bools allowed
    if key_l in {"raw_memory_graph", "private_fields_included", "private_core_imported"}:
        return False
    return any(banned in key_l for banned in _EXTRA_BANNED_FRAGMENTS)


def assert_no_forbidden_keys(obj: Any, *, path: str = "$") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if _is_forbidden_key(str(key)):
                # Allow explicit False attestation for raw_memory_graph style keys
                if str(key).lower() in {"raw_memory_graph", "private_fields_included"} and value is False:
                    continue
                if str(key).lower() in FORBIDDEN_PAYLOAD_KEYS:
                    # raw_memory_graph is in FORBIDDEN list — only False ok as attestation
                    if str(key).lower() == "raw_memory_graph" and value is False:
                        continue
                    raise ForbiddenPayloadKeyError(f"forbidden key at {path}.{key}")
                raise ForbiddenPayloadKeyError(f"forbidden key at {path}.{key}")
            assert_no_forbidden_keys(value, path=f"{path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            assert_no_forbidden_keys(item, path=f"{path}[{i}]")


def scrub_forbidden_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if _is_forbidden_key(str(key)):
                if str(key).lower() == "raw_memory_graph" and value is False:
                    out[key] = False
                continue
            out[key] = scrub_forbidden_keys(value)
        return out
    if isinstance(obj, list):
        return [scrub_forbidden_keys(x) for x in obj]
    return obj
