"""Honesty / display guards for PUB18-B Decision Detail transparency."""
from __future__ import annotations

from typing import Any

from backend.nexus_pub18_decision_detail.constants import (
    AI_POSTURES,
    AVAILABILITY_STATES,
    CHROME_LABELS,
    DISPLAY_PROVIDER_REQUIRED,
    DISPLAY_UNAVAILABLE,
    FRESHNESS_STATES,
)


class HonestyViolation(ValueError):
    """Raised when a presentation would violate an honesty hard ban."""


def format_optional_display(
    value: Any, *, available: bool, provider_required: bool = False
) -> str:
    """Format a display value. Unavailable / PROVIDER_REQUIRED never becomes '0'."""
    if provider_required:
        return DISPLAY_PROVIDER_REQUIRED
    if not available:
        return DISPLAY_UNAVAILABLE
    if value is None or value == "":
        return DISPLAY_UNAVAILABLE
    return str(value)


def assert_not_unavailable_as_zero(
    value: Any,
    *,
    available: bool,
    provider_required: bool = False,
    path: str = "value",
) -> None:
    if (not available or provider_required) and value in (0, "0", 0.0):
        raise HonestyViolation(f"unavailable_as_zero:{path}")


def assert_not_fake_live(*, mode: str, freshness: str, chrome_label: str) -> None:
    mode_u = (mode or "").upper()
    fresh_u = (freshness or "").upper()
    chrome_u = (chrome_label or "").upper()
    # Fixture / demo / unavailable modes must never wear LIVE chrome.
    if mode_u in {"DEMO_DATA", "FIXTURE", "PROVIDER_REQUIRED", "UNAVAILABLE"} and chrome_u in {
        "LIVE",
        "LIVE_READ_ONLY",
    }:
        raise HonestyViolation(f"fixture_as_live:{mode}->{chrome_label}")
    if fresh_u in {"PROVIDER_REQUIRED", "UNAVAILABLE", "DEMO_DATA", "FIXTURE"} and chrome_u in {
        "LIVE",
        "LIVE_READ_ONLY",
    }:
        raise HonestyViolation(f"unavailable_as_live:{freshness}->{chrome_label}")


def validate_posture(posture: str) -> str:
    p = (posture or "").upper()
    if p not in AI_POSTURES:
        raise HonestyViolation(f"invalid_ai_posture:{posture}")
    return p


def validate_freshness(freshness: str) -> str:
    f = (freshness or "").upper()
    if f not in FRESHNESS_STATES:
        raise HonestyViolation(f"invalid_freshness:{freshness}")
    return f


def validate_availability(availability: str) -> str:
    a = (availability or "").upper()
    if a not in AVAILABILITY_STATES:
        raise HonestyViolation(f"invalid_availability:{availability}")
    return a


def validate_chrome(chrome: str) -> str:
    c = (chrome or "").upper()
    if c not in CHROME_LABELS:
        raise HonestyViolation(f"invalid_chrome:{chrome}")
    return c


def build_metric_slot(
    *,
    key: str,
    value: Any,
    available: bool,
    provider_required: bool = False,
    unit: str | None = None,
) -> dict[str, Any]:
    """Build a metric slot that never fabricates LIVE zeros."""
    if provider_required:
        assert_not_unavailable_as_zero(value, available=False, provider_required=True, path=key)
        return {
            "key": key,
            "value": None,
            "display": DISPLAY_PROVIDER_REQUIRED,
            "available": False,
            "provider_required": True,
            "unit": unit,
            "status": "PROVIDER_REQUIRED",
        }
    if not available:
        assert_not_unavailable_as_zero(value, available=False, path=key)
        return {
            "key": key,
            "value": None,
            "display": DISPLAY_UNAVAILABLE,
            "available": False,
            "provider_required": False,
            "unit": unit,
            "status": "UNAVAILABLE",
        }
    return {
        "key": key,
        "value": value,
        "display": format_optional_display(value, available=True),
        "available": True,
        "provider_required": False,
        "unit": unit,
        "status": "AVAILABLE",
    }
