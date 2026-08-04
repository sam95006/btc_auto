"""Ratio helpers with explicit numerator/denominator/status (no empty-set 1.0)."""
from __future__ import annotations

from typing import Any

RATIO_STATUSES = frozenset(
    {"VALID", "NOT_APPLICABLE", "INSUFFICIENT_DENOMINATOR", "PROVIDER_BLOCKED"}
)


def make_ratio(
    numerator: int | float,
    denominator: int | float,
    *,
    min_denominator: int = 1,
    provider_blocked: bool = False,
) -> dict[str, Any]:
    n = float(numerator)
    d = float(denominator)
    if provider_blocked:
        return {
            "numerator": n,
            "denominator": d,
            "value": None,
            "status": "PROVIDER_BLOCKED",
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
