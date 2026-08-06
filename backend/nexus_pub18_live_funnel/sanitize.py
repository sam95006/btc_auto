"""Sanitize / forbidden Founder-field enforcement for PUB18-A."""
from __future__ import annotations

from typing import Any

from backend.nexus_pub18_live_funnel.constants import (
    EXECUTION_CONTROL_KEYS,
    FORBIDDEN_PAYLOAD_KEYS,
)


class ForbiddenPayloadKeyError(ValueError):
    """Raised when a banned Founder / private key appears in a member payload."""


_ATTESTATION_KEYS = frozenset(
    {
        "private_fields_included",
        "private_core_imported",
        "private_field_leak_count",
        "private_core_import_count",
        "execution_control_count",
        "member_execution_control_count",
        "private_contract_tip",
        "private_lessons_blocked",
        "founder_private_fields_blocked",
    }
)

_EXTRA_BANNED_FRAGMENTS = (
    "position_size",
    "leverage",
    "exact_entry",
    "exact_stop",
    "entry_price",
    "stop_loss",
    "stop_price",
    "take_profit",
    "order_id",
    "private_threshold",
    "proprietary_threshold",
    "strategy_source",
    "strategy_weight",
    "strategy_param",
    "lesson_memory",
    "private_lesson",
    "api_key",
    "api_secret",
    "private_key",
    "place_order",
    "trade_now",
    "execution_control",
)


def _is_forbidden_key(key: str) -> bool:
    key_l = str(key).lower()
    if key_l in _ATTESTATION_KEYS:
        return False
    if key_l in FORBIDDEN_PAYLOAD_KEYS:
        return True
    if key_l in EXECUTION_CONTROL_KEYS:
        return True
    return any(banned in key_l for banned in _EXTRA_BANNED_FRAGMENTS)


def assert_no_forbidden_keys(obj: Any, *, path: str = "$") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_s = str(key)
            if str(key).lower() in _ATTESTATION_KEYS:
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
            if str(key).lower() in _ATTESTATION_KEYS:
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
    hits: list[str] = []

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_s = str(key)
                next_path = f"{path}.{key_s}"
                if str(key).lower() in _ATTESTATION_KEYS:
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


def count_execution_controls(payload: Any) -> int:
    """Count top-level-ish execution-control exposures (truthy values only).

    Nested children under an already-counted control object are not double-counted.
    """
    count = 0

    def _walk(node: Any, *, under_control: bool = False) -> None:
        nonlocal count
        if isinstance(node, dict):
            for k, v in node.items():
                low = str(k).lower()
                is_control = low in EXECUTION_CONTROL_KEYS or any(
                    frag in low for frag in ("place_order", "trade_now", "trade_button", "auto_trade")
                )
                if is_control and not under_control and v not in (False, None, 0, "", [], {}):
                    count += 1
                    _walk(v, under_control=True)
                else:
                    _walk(v, under_control=under_control or is_control)
        elif isinstance(node, list):
            for x in node:
                _walk(x, under_control=under_control)

    _walk(payload)
    return count
