"""Event Study hard-block while R2 High residuals remain."""
from __future__ import annotations

EVENT_STUDY_STATUS = "NOT_READY"

REMAINING_HIGH_DISPOSITIONS = {
    # Lane C durability — hard-block production until dedicated DR cutover.
    "R2-C-003": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",
    "R2-C-004": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",
    "R2-C-006": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",
    "R2-C-007": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",
    # Collector Cutover V2 fixed these High residuals in-scope.
    "R2-D-003": "FIXED",
    "R2-D-005": "FIXED",
}


def assert_event_study_not_ready() -> None:
    if EVENT_STUDY_STATUS != "NOT_READY":
        raise RuntimeError("EVENT_STUDY_HARD_BLOCK: status must remain NOT_READY")
    if any(
        d not in {"FIXED", "BLOCKED_BY_DETERMINISTIC_GUARD", "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK"}
        for d in REMAINING_HIGH_DISPOSITIONS.values()
    ):
        raise RuntimeError("EVENT_STUDY_HARD_BLOCK: invalid High disposition")


def event_study_gate() -> dict:
    assert_event_study_not_ready()
    return {
        "event_study": EVENT_STUDY_STATUS,
        "remaining_high_dispositions": dict(REMAINING_HIGH_DISPOSITIONS),
        "raw_modified": False,
    }
