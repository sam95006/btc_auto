"""Bounded Demo session state machine for 6H V2 / 12H V3.

Forbidden transitions:
  RUNNING → RUNNING with deadline extension
  COMPLETED → RUNNING auto-reopen
  sharing one session_id across 6H and 12H
"""
from __future__ import annotations

from typing import FrozenSet

CREATED = "CREATED"
PREFLIGHT = "PREFLIGHT"
READY = "READY"
RUNNING = "RUNNING"
STOPPING = "STOPPING"
FLATTENING = "FLATTENING"
RECONCILING = "RECONCILING"
EXPORTING = "EXPORTING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
KILLED = "KILLED"

ALL_STATES: FrozenSet[str] = frozenset(
    {
        CREATED,
        PREFLIGHT,
        READY,
        RUNNING,
        STOPPING,
        FLATTENING,
        RECONCILING,
        EXPORTING,
        COMPLETED,
        FAILED,
        KILLED,
    }
)

ALLOWED_TRANSITIONS: dict[str, FrozenSet[str]] = {
    CREATED: frozenset({PREFLIGHT, FAILED, KILLED}),
    PREFLIGHT: frozenset({READY, FAILED, KILLED}),
    READY: frozenset({RUNNING, FAILED, KILLED}),
    RUNNING: frozenset({STOPPING, FLATTENING, FAILED, KILLED}),
    STOPPING: frozenset({FLATTENING, FAILED, KILLED}),
    FLATTENING: frozenset({RECONCILING, FAILED, KILLED}),
    RECONCILING: frozenset({EXPORTING, FAILED, KILLED}),
    EXPORTING: frozenset({COMPLETED, FAILED, KILLED}),
    COMPLETED: frozenset(),
    FAILED: frozenset(),
    KILLED: frozenset(),
}


class InvalidTransition(ValueError):
    pass


def can_transition(src: str, dst: str) -> bool:
    if src not in ALL_STATES or dst not in ALL_STATES:
        return False
    return dst in ALLOWED_TRANSITIONS.get(src, frozenset())


def transition(src: str, dst: str) -> str:
    if not can_transition(src, dst):
        raise InvalidTransition(f"{src} -> {dst} forbidden")
    # Explicit ban: no RUNNING self-loop (deadline extension).
    if src == RUNNING and dst == RUNNING:
        raise InvalidTransition("RUNNING cannot extend via RUNNING->RUNNING")
    if src == COMPLETED and dst == RUNNING:
        raise InvalidTransition("COMPLETED cannot auto-reopen to RUNNING")
    return dst
