"""Display honesty rules for PUB2-B live bindings."""
from __future__ import annotations

from typing import Any

UNAVAILABLE_STATES = frozenset({"UNAVAILABLE", "BLOCKED", "MISSING"})
STALE_STATES = frozenset({"STALE", "DEGRADED"})


def format_display_value(
    value: Any,
    *,
    freshness: str,
    completeness: str,
    allow_zero_when_available: bool = False,
) -> tuple[str, bool]:
    """Return (display_text, shown_as_zero).

    UNAVAILABLE/BLOCKED/MISSING must never render as numeric 0.
    """
    state = (freshness or "").upper()
    complete = (completeness or "").upper()
    unavailable = state in UNAVAILABLE_STATES or complete in {"MISSING", "BLOCKED"}

    if unavailable:
        if value is None or value == "" or value == 0 or value == 0.0 or value == "0":
            label = "BLOCKED" if state == "BLOCKED" or complete == "BLOCKED" else "UNAVAILABLE"
            return label, False
        # Non-zero policy labels (e.g. BLOCKED status string) are OK to show.
        return str(value), False

    if value is None or value == "":
        return "UNAVAILABLE", False

    if value == 0 or value == 0.0 or value == "0":
        if allow_zero_when_available:
            return "0", True
        # Zero without allow_zero under available state still displays 0 (legitimate).
        return "0", True

    return str(value), False


def requires_stale_indicator(freshness: str) -> bool:
    return (freshness or "").upper() in STALE_STATES


def is_unavailable_shown_as_zero(
    *,
    value: Any,
    freshness: str,
    completeness: str,
    display_text: str,
) -> bool:
    """True when an unavailable binding was incorrectly rendered as 0."""
    state = (freshness or "").upper()
    complete = (completeness or "").upper()
    unavailable = (
        state in UNAVAILABLE_STATES
        or complete in {"MISSING", "BLOCKED"}
        or value is None
    )
    if not unavailable:
        return False
    if display_text.strip() in {"0", "0.0", "0.00"}:
        return True
    if value in (0, 0.0, "0") and display_text.strip() not in {"UNAVAILABLE", "BLOCKED"}:
        return True
    return False
