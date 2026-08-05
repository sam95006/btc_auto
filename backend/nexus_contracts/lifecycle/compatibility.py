"""Terminal-state compatibility table across lifecycle scopes."""
from __future__ import annotations

from typing import Any, Literal

CompatStatus = Literal["compatible", "incompatible", "ambiguous", "n/a"]

# Rows are (scope_a, state_a, scope_b, state_b) → status
# Only terminal×terminal (or terminal×open-like conflict) pairs that matter for CI.
_TERMINAL_ROWS: tuple[tuple[str, str, str, str, CompatStatus, str], ...] = (
    # Decision CLOSED vs Position
    ("decision", "CLOSED", "position", "CLOSED", "compatible", "flat book after decision close"),
    ("decision", "CLOSED", "position", "NONE", "compatible", "no position opened"),
    ("decision", "CLOSED", "position", "LIQUIDATED_SIMULATED", "compatible", "simulated liquidation closed"),
    ("decision", "CLOSED", "position", "OPEN", "incompatible", "INV_DECISION_CLOSED_POSITION_OPEN"),
    ("decision", "CLOSED", "position", "OPENING", "incompatible", "INV_DECISION_CLOSED_POSITION_OPEN"),
    ("decision", "CLOSED", "position", "REDUCING", "incompatible", "INV_DECISION_CLOSED_POSITION_OPEN"),
    ("decision", "CLOSED", "position", "BLOCKED_AMBIGUOUS", "ambiguous", "must adjudicate before CLOSED"),
    # Session COMPLETED vs Intent
    ("session", "COMPLETED", "intent", "FILLED", "compatible", "intent resolved"),
    ("session", "COMPLETED", "intent", "CANCELLED", "compatible", "intent cancelled"),
    ("session", "COMPLETED", "intent", "REJECTED", "compatible", "intent rejected"),
    ("session", "COMPLETED", "intent", "EXPIRED", "compatible", "intent expired"),
    ("session", "COMPLETED", "intent", "SUPERSEDED", "compatible", "intent superseded"),
    ("session", "COMPLETED", "intent", "WORKING", "incompatible", "INV_SESSION_COMPLETED_UNRESOLVED_INTENT"),
    ("session", "COMPLETED", "intent", "DRAFT", "incompatible", "INV_SESSION_COMPLETED_UNRESOLVED_INTENT"),
    ("session", "COMPLETED", "intent", "SUBMITTED", "incompatible", "INV_SESSION_COMPLETED_UNRESOLVED_INTENT"),
    ("session", "COMPLETED", "intent", "ACCEPTED", "incompatible", "INV_SESSION_COMPLETED_UNRESOLVED_INTENT"),
    ("session", "COMPLETED", "intent", "PARTIAL", "incompatible", "INV_SESSION_COMPLETED_UNRESOLVED_INTENT"),
    ("session", "COMPLETED", "intent", "BLOCKED_AMBIGUOUS", "incompatible", "INV_SESSION_COMPLETED_UNRESOLVED_INTENT"),
    # Session COMPLETED vs Position
    ("session", "COMPLETED", "position", "CLOSED", "compatible", "flat"),
    ("session", "COMPLETED", "position", "NONE", "compatible", "never opened"),
    ("session", "COMPLETED", "position", "OPEN", "incompatible", "INV_SESSION_COMPLETED_OPEN_POSITION"),
    # Reflection COMPLETE vs exit
    ("reflection", "COMPLETE", "decision", "EXITED", "compatible", "exit evidence present"),
    ("reflection", "COMPLETE", "decision", "CLOSED", "compatible", "exit evidence present"),
    ("reflection", "COMPLETE", "decision", "MONITORING", "incompatible", "INV_REFLECTION_COMPLETE_BEFORE_EXIT"),
    ("reflection", "COMPLETE", "decision", "APPROVED_SIMULATED", "incompatible", "INV_REFLECTION_COMPLETE_BEFORE_EXIT"),
    ("reflection", "COMPLETE", "decision", "OBSERVED", "incompatible", "INV_REFLECTION_COMPLETE_BEFORE_EXIT"),
    # Position CLOSED residual handled via qty invariant (not state pair)
    ("position", "CLOSED", "session", "COMPLETED", "compatible", "qty must be 0 separately"),
    ("position", "CLOSED", "session", "RUNNING", "compatible", "other positions may remain"),
    # Session vs ControlPlane terminals via adapter
    ("session", "COMPLETED", "control_plane", "STOPPED", "compatible", "adapter equivalent"),
    ("session", "COMPLETED", "control_plane", "KILLED", "incompatible", "adapter relation=none"),
    ("session", "FAILED_SAFE", "control_plane", "FAILED_SAFE", "compatible", "adapter equivalent"),
    ("session", "BLOCKED", "control_plane", "FAILED_SAFE", "compatible", "adapter session_implies_control"),
    ("session", "BLOCKED", "control_plane", "STOPPED", "incompatible", "unmapped"),
)


TERMINAL_COMPATIBILITY_TABLE: tuple[dict[str, str], ...] = tuple(
    {
        "scope_a": a,
        "state_a": sa,
        "scope_b": b,
        "state_b": sb,
        "status": status,
        "note": note,
    }
    for a, sa, b, sb, status, note in _TERMINAL_ROWS
)


def terminal_pair_status(
    scope_a: str, state_a: str, scope_b: str, state_b: str
) -> CompatStatus:
    for row in TERMINAL_COMPATIBILITY_TABLE:
        if (
            row["scope_a"] == scope_a
            and row["state_a"] == state_a
            and row["scope_b"] == scope_b
            and row["state_b"] == state_b
        ):
            return row["status"]  # type: ignore[return-value]
        # symmetric lookup
        if (
            row["scope_a"] == scope_b
            and row["state_a"] == state_b
            and row["scope_b"] == scope_a
            and row["state_b"] == state_a
        ):
            return row["status"]  # type: ignore[return-value]
    return "n/a"


def compatibility_report() -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in TERMINAL_COMPATIBILITY_TABLE:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema": "nexus_lifecycle_terminal_compatibility_v11_1",
        "row_count": len(TERMINAL_COMPATIBILITY_TABLE),
        "status_counts": counts,
        "rows": list(TERMINAL_COMPATIBILITY_TABLE),
    }
