"""Allow-list serializer — only public fields survive."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from backend.nexus_publishing_gateway.constants import ALLOWED_PUBLIC_FIELDS
from backend.nexus_publishing_gateway.deny_traps import normalize_field_name


def _coerce(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return obj


def serialize_allowlist(payload: Any, *, drop_unknown: bool = True) -> Any:
    """Deep-copy payload keeping only allow-listed keys.

    Unknown keys are dropped by default (allow-list, not deny-list).
    Nested dicts are recursively filtered. Lists are mapped element-wise.
    Scalars pass through unchanged.
    """
    obj = _coerce(payload)
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            norm = normalize_field_name(k)
            if norm in ALLOWED_PUBLIC_FIELDS:
                out[norm] = serialize_allowlist(v, drop_unknown=drop_unknown)
            elif not drop_unknown:
                # Explicit non-drop mode still refuses non-allowlisted keys.
                continue
        return out
    if isinstance(obj, list):
        return [serialize_allowlist(x, drop_unknown=drop_unknown) for x in obj]
    if isinstance(obj, tuple):
        return [serialize_allowlist(x, drop_unknown=drop_unknown) for x in obj]
    return obj


def collect_public_field_names(payload: Any) -> set[str]:
    obj = serialize_allowlist(payload)
    names: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                names.add(str(k))
                _walk(v)
        elif isinstance(node, list):
            for x in node:
                _walk(x)

    _walk(obj)
    return names
