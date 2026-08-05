"""Deny-list traps for private / forbidden fields."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from typing import Any

from backend.nexus_publishing_gateway.constants import DENIED_PRIVATE_FIELDS
from backend.nexus_publishing_gateway.exceptions import DenyTrapError

_SECRET_VALUE_RE = re.compile(
    r"(?i)(sk-[a-z0-9]{16,}|api[_-]?key\s*[:=]\s*\S+|bearer\s+[a-z0-9\-._~+/]+=*)"
)


def walk_keys(obj: Any, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            keys.append(str(k))
            keys.extend(walk_keys(v, path))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            keys.extend(walk_keys(v, f"{prefix}[{i}]"))
    elif is_dataclass(obj) and not isinstance(obj, type):
        keys.extend(walk_keys(asdict(obj), prefix))
    return keys


def normalize_field_name(name: str) -> str:
    return str(name).strip().lower().replace("-", "_")


def find_denied_fields(payload: Any) -> list[str]:
    if is_dataclass(payload) and not isinstance(payload, type):
        data = asdict(payload)
    elif isinstance(payload, dict):
        data = payload
    else:
        data = {"_value": payload}

    hits: set[str] = set()
    for key in walk_keys(data):
        norm = normalize_field_name(key)
        if norm in DENIED_PRIVATE_FIELDS:
            hits.add(norm)

    blob = json.dumps(data, default=str)
    lower = blob.lower()
    for denied in DENIED_PRIVATE_FIELDS:
        # Key-style markers only (avoid false positives on free text where possible).
        if f'"{denied}"' in lower or f"'{denied}'" in lower:
            hits.add(denied)
    if _SECRET_VALUE_RE.search(blob):
        hits.add("secret_value_pattern")
    return sorted(hits)


def assert_no_denied_fields(payload: Any, *, context: str = "publish") -> dict[str, Any]:
    hits = find_denied_fields(payload)
    if hits:
        raise DenyTrapError(f"{context}:denied_fields:{','.join(hits)}")
    return {"ok": True, "context": context, "denied_hits": 0}
