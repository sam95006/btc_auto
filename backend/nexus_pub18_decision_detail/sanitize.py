"""Sanitize / forbidden private-field enforcement for PUB18-B Decision Detail."""
from __future__ import annotations

from typing import Any

from backend.nexus_pub18_decision_detail.constants import FORBIDDEN_PAYLOAD_KEYS


class ForbiddenPayloadKeyError(ValueError):
    """Raised when a banned private key appears in a member payload."""


_EXTRA_BANNED_FRAGMENTS = (
    "private_raw_graph",
    "raw_graph",
    "memory_graph",
    "graph_nodes",
    "graph_edges",
    "proprietary_threshold",
    "private_threshold",
    "threshold_table",
    "strategy_weight",
    "strategy_param",
    "founder_entry",
    "founder_exit",
    "exact_entry",
    "exact_exit",
    "entry_price",
    "exit_price",
    "stop_loss",
    "stop_price",
    "take_profit",
    "internal_prompt",
    "system_prompt",
    "raw_provider_prompt",
    "raw_cot",
    "chain_of_thought",
    "account_data",
    "account_balance",
    "wallet_address",
    "api_key",
    "api_secret",
    "private_key",
    "order_id",
    "leverage",
    "position_size",
    "lesson_memory",
)


# Attestation / meta keys that mention "private" / "lesson" but are allowed
# as explicit public-safety flags (always False / blocked semantics).
_ATTESTATION_KEYS = frozenset(
    {
        "private_fields_included",
        "private_core_imported",
        "private_field_leak_count",
        "private_core_import_count",
        "founder_private_fields_blocked",
        "private_fields_blocked",
        "private_lesson_memory",
    }
)


def _is_forbidden_key(key: str) -> bool:
    key_l = str(key).lower()
    if key_l in _ATTESTATION_KEYS:
        return False
    if key_l in FORBIDDEN_PAYLOAD_KEYS:
        return True
    return any(banned in key_l for banned in _EXTRA_BANNED_FRAGMENTS)


def assert_no_forbidden_keys(obj: Any, *, path: str = "$") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_s = str(key)
            key_l = key_s.lower()
            if key_l in _ATTESTATION_KEYS:
                assert_no_forbidden_keys(value, path=f"{path}.{key_s}")
                continue
            if _is_forbidden_key(key_s):
                raise ForbiddenPayloadKeyError(f"forbidden key at {path}.{key_s}")
            assert_no_forbidden_keys(value, path=f"{path}.{key_s}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            assert_no_forbidden_keys(item, path=f"{path}[{i}]")


def scrub_forbidden_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            key_l = str(key).lower()
            if key_l in _ATTESTATION_KEYS:
                out[key] = scrub_forbidden_keys(value)
                continue
            if _is_forbidden_key(str(key)):
                continue
            out[key] = scrub_forbidden_keys(value)
        return out
    if isinstance(obj, list):
        return [scrub_forbidden_keys(x) for x in obj]
    return obj


def count_forbidden_key_hits(obj: Any) -> list[str]:
    """Return dotted paths of forbidden keys (for leak attestation)."""
    hits: list[str] = []

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_s = str(key)
                key_l = key_s.lower()
                next_path = f"{path}.{key_s}"
                if key_l in _ATTESTATION_KEYS:
                    _walk(value, next_path)
                    continue
                if _is_forbidden_key(key_s):
                    hits.append(next_path)
                else:
                    _walk(value, next_path)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk(item, f"{path}[{i}]")

    _walk(obj, "$")
    return hits
