"""Payload sanitization for PUB2-A Decision Product E2E."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_decision_product.constants import FORBIDDEN_PAYLOAD_KEYS

# Boolean attestation flags (False = compliant). Not payload data fields.
_ATTESTATION_BOOL_KEYS = frozenset(
    {
        "fabricated_customers",
        "fabricated_metrics",
        "customer_trading",
        "exchange_api_used",
        "private_core_imported",
        "places_orders",
        "auto_trades",
        "private_lesson_memory",
        "execution_controls",
        "read_only",
    }
)


class ForbiddenPayloadKeyError(ValueError):
    """Raised when a banned key appears in a Decision Product payload."""


def assert_no_forbidden_keys(obj: Any, *, path: str = "$") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_l = str(key).lower()
            if key_l in _ATTESTATION_BOOL_KEYS:
                assert_no_forbidden_keys(value, path=f"{path}.{key}")
                continue
            if key_l in FORBIDDEN_PAYLOAD_KEYS or any(
                banned in key_l
                for banned in (
                    "api_key",
                    "api_secret",
                    "private_key",
                    "strategy_weight",
                )
            ):
                raise ForbiddenPayloadKeyError(f"forbidden key at {path}.{key}")
            # Singular fabrication injection keys (not plural attestation flags)
            if key_l in {"fabricated_customer", "fabricated_metric"} or key_l.startswith(
                "fabricated_customer_"
            ):
                raise ForbiddenPayloadKeyError(f"forbidden key at {path}.{key}")
            assert_no_forbidden_keys(value, path=f"{path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            assert_no_forbidden_keys(item, path=f"{path}[{i}]")


def assert_no_execution_controls(payload: dict[str, Any]) -> None:
    """Journey stages must never expose execution controls."""
    banned_truthy = (
        "places_orders",
        "customer_trading",
        "exchange_api_used",
        "auto_trades",
        "execution_enabled",
        "order_placement_enabled",
        "demo_orders",
        "shadow_orders",
        "mainnet",
    )
    for key in banned_truthy:
        if payload.get(key) is True:
            raise ForbiddenPayloadKeyError(f"execution control enabled: {key}")
    controls = payload.get("execution_controls")
    if controls:
        raise ForbiddenPayloadKeyError("execution_controls must be absent or empty")
