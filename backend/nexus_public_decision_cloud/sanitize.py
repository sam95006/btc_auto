"""Payload sanitization for Public Decision Cloud."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_decision_cloud.constants import FORBIDDEN_PAYLOAD_KEYS


class ForbiddenPayloadKeyError(ValueError):
    """Raised when a banned key appears in a Decision Cloud payload."""


def assert_no_forbidden_keys(obj: Any, *, path: str = "$") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_l = str(key).lower()
            if key_l in FORBIDDEN_PAYLOAD_KEYS or any(
                banned in key_l for banned in ("api_key", "api_secret", "private_key", "strategy_weight")
            ):
                raise ForbiddenPayloadKeyError(f"forbidden key at {path}.{key}")
            assert_no_forbidden_keys(value, path=f"{path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            assert_no_forbidden_keys(item, path=f"{path}[{i}]")
