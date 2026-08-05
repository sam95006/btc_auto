"""Sanitize / allow-list enforcement for Public Intelligence DTO V2."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_intelligence_dto_v2.constants import (
    ALLOWED_PUBLIC_FIELDS,
    DENIED_PRIVATE_FIELDS,
)


class ForbiddenPayloadKeyError(ValueError):
    """Raised when a denied private field appears in a public payload."""


def normalize_field_name(name: str) -> str:
    return str(name).strip()


def assert_no_forbidden_keys(payload: Any, *, path: str = "root") -> None:
    """Fail-closed if any denied private field name is present."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            norm = normalize_field_name(key)
            low = norm.lower()
            if low in DENIED_PRIVATE_FIELDS or norm in DENIED_PRIVATE_FIELDS:
                raise ForbiddenPayloadKeyError(f"{path}.{norm}")
            # raw_memory_graph may appear only as explicit False
            if low == "raw_memory_graph" and value not in (False, None, 0):
                raise ForbiddenPayloadKeyError(f"{path}.{norm}:truthy_raw_memory_graph")
            if low == "private_fields_included" and value not in (False, None, 0):
                raise ForbiddenPayloadKeyError(f"{path}.{norm}:private_fields_included")
            assert_no_forbidden_keys(value, path=f"{path}.{norm}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            assert_no_forbidden_keys(item, path=f"{path}[{i}]")


def serialize_allowlist(payload: Any) -> Any:
    """Deep-copy keeping only allow-listed keys (allow-list, not deny-list)."""
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            norm = normalize_field_name(key)
            if norm in ALLOWED_PUBLIC_FIELDS:
                out[norm] = serialize_allowlist(value)
        return out
    if isinstance(payload, list):
        return [serialize_allowlist(x) for x in payload]
    if isinstance(payload, tuple):
        return [serialize_allowlist(x) for x in payload]
    return payload


def collect_field_names(payload: Any) -> set[str]:
    names: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                names.add(str(k))
                _walk(v)
        elif isinstance(node, list):
            for x in node:
                _walk(x)

    _walk(payload)
    return names


def assert_allowlisted_only(payload: Any) -> None:
    """Every key in the serialized payload must be in ALLOWED_PUBLIC_FIELDS."""
    filtered = serialize_allowlist(payload)
    unknown = collect_field_names(filtered) - ALLOWED_PUBLIC_FIELDS
    if unknown:
        raise ForbiddenPayloadKeyError(f"unknown_public_fields:{sorted(unknown)}")
    assert_no_forbidden_keys(filtered)
