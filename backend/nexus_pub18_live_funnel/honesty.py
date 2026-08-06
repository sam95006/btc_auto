"""Honesty / display guards for PUB18-A Live Funnel first screen."""
from __future__ import annotations

from typing import Any

from backend.nexus_pub18_live_funnel.constants import (
    AI_POSTURES,
    DATA_CLASS_LABELS,
    DISPLAY_LIVE_READ_ONLY,
    DISPLAY_STALE,
    DISPLAY_UNAVAILABLE,
)


class HonestyViolation(ValueError):
    """Raised when a presentation would violate an honesty hard ban."""


def validate_posture(posture: str) -> str:
    p = (posture or "").upper()
    if p not in AI_POSTURES:
        raise HonestyViolation(f"invalid_ai_posture:{posture}")
    return p


def validate_data_class(label: str) -> str:
    u = (label or "").upper()
    if u not in DATA_CLASS_LABELS:
        raise HonestyViolation(f"invalid_data_class:{label}")
    return u


def assert_not_unavailable_as_zero(
    value: Any,
    *,
    available: bool,
    path: str = "value",
) -> None:
    if (not available) and value in (0, "0", 0.0):
        raise HonestyViolation(f"unavailable_as_zero:{path}")


def assert_not_fake_live(*, data_class: str, chrome_label: str) -> None:
    """FIXTURE / UNAVAILABLE / STALE must never wear LIVE chrome."""
    dc = validate_data_class(data_class)
    chrome = (chrome_label or "").upper()
    if chrome == "LIVE":
        # Bare LIVE is banned; only LIVE_READ_ONLY is honest.
        raise HonestyViolation(f"bare_live_forbidden:{chrome_label}")
    if dc in {"FIXTURE", "UNAVAILABLE", "STALE"} and chrome == "LIVE_READ_ONLY":
        raise HonestyViolation(f"fixture_as_live:{dc}->{chrome_label}")
    if dc == "LIVE_READ_ONLY" and chrome not in {"LIVE_READ_ONLY"}:
        raise HonestyViolation(f"live_mislabel:{dc}->{chrome_label}")


def format_stage_display(*, count: Any, available: bool, data_class: str) -> str:
    """Format a funnel stage count. Unavailable never becomes '0'."""
    if not available:
        dc = (data_class or "").upper()
        if dc == "STALE":
            return DISPLAY_STALE
        if dc == "UNAVAILABLE":
            return DISPLAY_UNAVAILABLE
        return DISPLAY_UNAVAILABLE
    if count is None:
        return DISPLAY_UNAVAILABLE
    return str(int(count))


def build_metric_slot(
    *,
    key: str,
    value: Any,
    available: bool,
    provider_required: bool = False,
    unit: str | None = None,
) -> dict[str, Any]:
    if provider_required or not available:
        assert_not_unavailable_as_zero(value, available=False, path=key)
        label = "PROVIDER_REQUIRED" if provider_required else DISPLAY_UNAVAILABLE
        return {
            "key": key,
            "value": None,
            "display": label,
            "available": False,
            "provider_required": bool(provider_required),
            "unit": unit,
            "status": label,
        }
    return {
        "key": key,
        "value": value,
        "display": str(value) if value is not None else DISPLAY_UNAVAILABLE,
        "available": True,
        "provider_required": False,
        "unit": unit,
        "status": "AVAILABLE",
    }


def chrome_for_data_class(data_class: str) -> str:
    dc = validate_data_class(data_class)
    if dc == "LIVE_READ_ONLY":
        return DISPLAY_LIVE_READ_ONLY
    if dc == "STALE":
        return DISPLAY_STALE
    if dc == "FIXTURE":
        return "FIXTURE"
    return DISPLAY_UNAVAILABLE
