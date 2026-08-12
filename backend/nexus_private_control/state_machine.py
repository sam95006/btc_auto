"""Fail-closed state machine for Founder-private control plane lifecycle."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


CANONICAL_STATES: tuple[str, ...] = (
    "IDLE",
    "STARTING",
    "RUNNING",
    "PAUSED",
    "RECOVERING",
    "STOPPING",
    "STOPPED",
    "KILLED",
    "FAILED_SAFE",
)

TERMINAL_STATES: frozenset[str] = frozenset({"STOPPED", "KILLED", "FAILED_SAFE"})

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "IDLE": frozenset({"STARTING", "FAILED_SAFE"}),
    "STARTING": frozenset({"RUNNING", "FAILED_SAFE", "KILLED"}),
    "RUNNING": frozenset({"PAUSED", "RECOVERING", "STOPPING", "KILLED", "FAILED_SAFE"}),
    "PAUSED": frozenset({"RUNNING", "RECOVERING", "STOPPING", "KILLED", "FAILED_SAFE"}),
    "RECOVERING": frozenset({"RUNNING", "STOPPING", "KILLED", "FAILED_SAFE"}),
    "STOPPING": frozenset({"STOPPED", "FAILED_SAFE", "KILLED"}),
    "STOPPED": frozenset(),
    "KILLED": frozenset(),
    "FAILED_SAFE": frozenset(),
}


class InvalidTransitionError(Exception):
    """Illegal lifecycle transition — fail closed, no silent mutation."""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class TransitionRecord:
    previous_state: str
    next_state: str
    timestamp: str
    reason: str
    command: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_state": self.previous_state,
            "next_state": self.next_state,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "command": self.command,
            "metadata": dict(self.metadata),
        }


class ControlPlaneStateMachine:
    """Thread-safe fail-closed lifecycle for the private control plane."""

    def __init__(self, *, initial: str = "IDLE") -> None:
        if initial not in CANONICAL_STATES:
            raise InvalidTransitionError(f"unknown_initial_state:{initial}")
        self._lock = threading.RLock()
        self._state = initial
        self._history: list[TransitionRecord] = []

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._history]

    def transition(
        self,
        next_state: str,
        *,
        command: str,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> TransitionRecord:
        with self._lock:
            if next_state not in CANONICAL_STATES:
                raise InvalidTransitionError(f"unknown_target_state:{next_state}")
            allowed = VALID_TRANSITIONS.get(self._state, frozenset())
            if next_state not in allowed:
                raise InvalidTransitionError(
                    f"invalid_transition:{self._state}->{next_state}:command={command}"
                )
            record = TransitionRecord(
                previous_state=self._state,
                next_state=next_state,
                timestamp=_utc(),
                reason=reason or command,
                command=command,
                metadata=dict(metadata or {}),
            )
            self._state = next_state
            self._history.append(record)
            return record
