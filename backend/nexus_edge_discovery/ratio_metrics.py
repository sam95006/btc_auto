"""Ratio helpers with explicit numerator/denominator/status (no empty-set 1.0)."""
from __future__ import annotations

from typing import Any

RATIO_STATUSES = frozenset(
    {
        "VALID",
        "NOT_APPLICABLE",
        "INSUFFICIENT_DENOMINATOR",
        "PROVIDER_BLOCKED",
        "GROQ_PROVIDER_BLOCKED",
        "SAMBANOVA_PROVIDER_BLOCKED",
        "PROVIDER_CAPACITY_UNKNOWN",
        "INCOMPLETE_SAMPLE",
    }
)

_BLOCKED_NO_VALUE = frozenset(
    {
        "PROVIDER_BLOCKED",
        "GROQ_PROVIDER_BLOCKED",
        "SAMBANOVA_PROVIDER_BLOCKED",
        "PROVIDER_CAPACITY_UNKNOWN",
        "NOT_APPLICABLE",
    }
)


def make_ratio(
    numerator: int | float,
    denominator: int | float,
    *,
    min_denominator: int = 1,
    status_override: str | None = None,
    provider_blocked: bool = False,
    provider_block_status: str = "PROVIDER_BLOCKED",
) -> dict[str, Any]:
    n = float(numerator)
    d = float(denominator)
    if status_override:
        if status_override not in RATIO_STATUSES:
            raise ValueError(f"unknown ratio status: {status_override}")
        value = (n / d) if d > 0 and status_override not in _BLOCKED_NO_VALUE else None
        return {
            "numerator": n,
            "denominator": d,
            "value": value,
            "status": status_override,
        }
    if provider_blocked:
        status = (
            provider_block_status
            if provider_block_status in RATIO_STATUSES
            else "PROVIDER_BLOCKED"
        )
        return {
            "numerator": n,
            "denominator": d,
            "value": None,
            "status": status,
        }
    if d <= 0:
        return {
            "numerator": n,
            "denominator": 0,
            "value": None,
            "status": "NOT_APPLICABLE",
        }
    if d < min_denominator:
        return {
            "numerator": n,
            "denominator": d,
            "value": None,
            "status": "INSUFFICIENT_DENOMINATOR",
        }
    return {
        "numerator": n,
        "denominator": d,
        "value": n / d,
        "status": "VALID",
    }


def ratio_value_or_none(ratio: dict[str, Any]) -> float | None:
    if ratio.get("status") != "VALID":
        return None
    return ratio.get("value")
