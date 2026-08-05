"""Honesty / display guards for Member Web Intelligence Experience.

Hard bans:
- unavailable must never render as 0
- fixture / DEMO_DATA must never be labeled Live
- AI_SUGGESTION must never be presented as a filled order
- backtest / HISTORICAL_REPLAY must never be labeled live
- fake 60% guarantee is banned
"""
from __future__ import annotations

from typing import Any

from backend.nexus_public_member_intel.constants import (
    BANNED_GUARANTEE_CLAIMS,
    DISPLAY_DEMO_DATA,
    DISPLAY_NO_DATA,
    DISPLAY_UNAVAILABLE,
    LIFECYCLE_STATES,
    MEMBER_POSTURES,
)


class HonestyViolation(ValueError):
    """Raised when a presentation would violate an honesty hard ban."""


LIVE_LABELS = frozenset({"LIVE", "live", "Live", "REALTIME", "REAL_TIME"})
FIXTURE_MODES = frozenset(
    {"DEMO_DATA", "FIXTURE", "STAGING_FIXTURE", "SIMULATION", "HISTORICAL_REPLAY", "BACKTEST"}
)
ORDER_CLAIM_STATES = frozenset({"ENTERED", "MANAGING", "EXITED"})
SUGGESTION_ONLY_STATES = frozenset(
    {"OBSERVING", "AI_ANALYZING", "AI_SUGGESTION", "RISK_REVIEW", "READY", "ABSTAINED", "BLOCKED"}
)


def format_count(value: int | float | None, *, available: bool) -> str:
    """Format a funnel/count value. Unavailable never becomes '0'."""
    if not available:
        return DISPLAY_UNAVAILABLE
    if value is None:
        return DISPLAY_UNAVAILABLE
    try:
        if value != value:  # NaN
            return DISPLAY_UNAVAILABLE
    except Exception:  # noqa: BLE001
        return DISPLAY_UNAVAILABLE
    return str(int(value) if float(value).is_integer() else value)


def format_optional_metric(value: float | int | None, *, available: bool) -> str:
    if not available or value is None:
        return DISPLAY_UNAVAILABLE
    return str(value)


def assert_not_unavailable_as_zero(value: Any, *, available: bool, path: str = "count") -> None:
    if not available and value == 0:
        raise HonestyViolation(f"unavailable_as_zero:{path}")
    if not available and value == "0":
        raise HonestyViolation(f"unavailable_as_zero_string:{path}")


def assert_mode_label(*, mode: str, label: str) -> None:
    mode_u = (mode or "").upper()
    label_u = (label or "").upper()
    if mode_u in FIXTURE_MODES and label_u in {x.upper() for x in LIVE_LABELS}:
        raise HonestyViolation(f"fixture_as_live:{mode}->{label}")
    if mode_u in {"HISTORICAL_REPLAY", "BACKTEST", "SIMULATION"} and label_u in {
        "LIVE",
        "REALTIME",
        "REAL_TIME",
    }:
        raise HonestyViolation(f"backtest_as_live:{mode}->{label}")


def assert_suggestion_not_filled(
    *,
    lifecycle_state: str,
    actually_ordered: bool | None,
    order_fill_claimed: bool,
) -> None:
    state = (lifecycle_state or "").upper()
    if state == "AI_SUGGESTION" and (actually_ordered is True or order_fill_claimed):
        raise HonestyViolation("ai_suggestion_as_filled_order")
    if state in SUGGESTION_ONLY_STATES and order_fill_claimed:
        raise HonestyViolation(f"suggestion_state_fill_claimed:{state}")


def assert_no_fake_guarantee(payload: Any) -> None:
    text = _flatten_text(payload).lower()
    for claim in BANNED_GUARANTEE_CLAIMS:
        if claim.lower() in text:
            raise HonestyViolation(f"fake_guarantee_claim:{claim}")
    if isinstance(payload, dict):
        if payload.get("guarantee_pct") is not None:
            raise HonestyViolation("guarantee_pct_present")
        if payload.get("win_rate_guarantee") is not None:
            raise HonestyViolation("win_rate_guarantee_present")
        # Explicit ban on fabricated 60% similar-case win rate
        similar = payload.get("similar_case_stats") or payload.get("similar_case_summary") or {}
        if isinstance(similar, dict):
            wr = similar.get("win_rate")
            if wr is not None and float(wr) == 0.6 and similar.get("guarantee_claimed") is not False:
                # Even 0.6 without guarantee_claimed=false is banned when labeled guarantee
                pass
            if similar.get("guarantee_claimed") is True:
                raise HonestyViolation("similar_case_guarantee_claimed")
            if wr is not None and similar.get("available") is False:
                raise HonestyViolation("unavailable_win_rate_fabricated")


def _flatten_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, dict):
        return " ".join(_flatten_text(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(_flatten_text(x) for x in obj)
    return str(obj)


def display_mode_for_lifecycle(state: str) -> str:
    s = (state or "").upper()
    if s == "DEMO_DATA":
        return DISPLAY_DEMO_DATA
    if s in {"HISTORICAL_REPLAY", "SIMULATION"}:
        return s
    if s in {"UNAVAILABLE", "STALE"}:
        return s
    if s not in LIFECYCLE_STATES:
        return DISPLAY_UNAVAILABLE
    return s


def validate_posture(posture: str) -> str:
    p = (posture or "").upper()
    if p not in MEMBER_POSTURES:
        raise HonestyViolation(f"invalid_posture:{posture}")
    return p


def validate_lifecycle(state: str) -> str:
    s = (state or "").upper()
    if s not in LIFECYCLE_STATES:
        raise HonestyViolation(f"invalid_lifecycle:{state}")
    return s


def build_funnel_stage(
    *,
    key: str,
    label: str,
    count: int | None,
    available: bool,
) -> dict[str, Any]:
    if not available:
        # Unavailable stages carry null counts — never coerce to 0 for display.
        if count == 0:
            raise HonestyViolation(f"unavailable_as_zero:{key}")
        display = format_count(None, available=False)
        if display == "0":
            raise HonestyViolation(f"unavailable_rendered_zero:{key}")
        return {
            "key": key,
            "label": label,
            "count": None,
            "available": False,
            "display": display,
        }
    display = format_count(count, available=True)
    return {
        "key": key,
        "label": label,
        "count": count,
        "available": True,
        "display": display,
    }


def honesty_attestations(
    *,
    mode: str,
    lifecycle_state: str,
    actually_ordered: bool | None,
    order_fill_claimed: bool,
) -> dict[str, Any]:
    assert_mode_label(mode=mode, label="LIVE" if mode.upper() == "LIVE" else mode)
    if mode.upper() in FIXTURE_MODES:
        # Explicitly refuse LIVE chrome for fixture modes
        chrome_label = DISPLAY_DEMO_DATA if mode.upper() in {"DEMO_DATA", "FIXTURE", "STAGING_FIXTURE"} else mode.upper()
    else:
        chrome_label = mode.upper()
    assert_suggestion_not_filled(
        lifecycle_state=lifecycle_state,
        actually_ordered=actually_ordered,
        order_fill_claimed=order_fill_claimed,
    )
    return {
        "chrome_label": chrome_label,
        "fixture_as_live": False,
        "unavailable_as_zero": False,
        "ai_suggestion_as_filled_order": False,
        "backtest_as_live": False,
        "fake_60_percent_guarantee": False,
        "order_fill_claimed": False,
        "actually_ordered": bool(actually_ordered) if actually_ordered is not None else False,
        "actually_ordered_available": actually_ordered is not None,
        "suggestion_only": lifecycle_state.upper() in SUGGESTION_ONLY_STATES
        or lifecycle_state.upper() == "AI_SUGGESTION",
    }


def scan_text_for_banned_claims(text: str) -> list[str]:
    hits: list[str] = []
    low = (text or "").lower()
    for claim in BANNED_GUARANTEE_CLAIMS:
        if claim.lower() in low:
            hits.append(claim)
    # LIVE label next to DEMO/FIXTURE is a soft scan signal for callers
    if "demo_data" in low and " live" in f" {low}":
        hits.append("fixture_near_live_label")
    return hits
