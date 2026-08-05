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

# Short tokens that must NEVER be matched via JSON substring (value false positives).
_BLOB_SCAN_DENYLIST: frozenset[str] = frozenset(
    {
        "strategy_id",
        "strategy_ids",
        "strategy_parameters",
        "strategy_params",
        "strategy_weights",
        "lesson_id",
        "lesson_ids",
        "private_lesson_id",
        "lesson_memory",
        "raw_provider_prompt",
        "raw_provider_response",
        "system_prompt",
        "order_id",
        "order_ids",
        "order_link_id",
        "position_id",
        "wallet_address",
        "wallet_data",
        "account_id",
        "account_data",
        "api_key",
        "api_secret",
        "api_passphrase",
        "provider_secret",
        "provider_secrets",
        "private_key",
        "execution_route",
        "execution_routes",
        "routing_table",
        "private_risk",
        "private_risk_internals",
        "risk_governor_state",
        "risk_internals",
        "member_id",
    }
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
    """Normalize snake, kebab, and camelCase field names to snake_case."""
    s = str(name).strip().replace("-", "_")
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return s.lower().replace("__", "_")


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
    # Only long/explicit private key markers in JSON text — avoids "order"/"route" value FPs.
    lower = blob.lower()
    for denied in _BLOB_SCAN_DENYLIST:
        if f'"{denied}"' in lower or f"'{denied}'" in lower:
            hits.add(denied)
    if _SECRET_VALUE_RE.search(blob):
        hits.add("secret_value_pattern")
    return sorted(hits)


def assert_no_denied_fields(payload: Any, *, context: str = "publish") -> dict[str, Any]:
    hits = find_denied_fields(payload)
    if hits:
        # Field names only — never echo values (side-channel safe).
        raise DenyTrapError(f"{context}:denied_fields:{','.join(hits)}")
    return {"ok": True, "context": context, "denied_hits": 0}
