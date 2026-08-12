"""Formal state machine for Live Shadow Runtime Conductor (§4.1)."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.nexus_live_shadow_runtime.constants import (
    RUNTIME_STATES,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
)


class InvalidRuntimeTransitionError(Exception):
    """Illegal lifecycle transition — fail closed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class TransitionRecord:
    previous_state: str
    next_state: str
    timestamp: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_state": self.previous_state,
            "next_state": self.next_state,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


class RuntimeStateMachine:
    """Thread-safe fail-closed lifecycle for the Live Shadow Runtime Conductor."""

    def __init__(self, *, initial: str = "STARTING") -> None:
        if initial not in RUNTIME_STATES:
            raise InvalidRuntimeTransitionError(f"unknown_initial_state:{initial}")
        self._lock = threading.RLock()
        self._state = initial
        self._history: list[TransitionRecord] = []
        self._failure_reason: str | None = None

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def failure_reason(self) -> str | None:
        with self._lock:
            return self._failure_reason

    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._history]

    def transition(
        self,
        next_state: str,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> TransitionRecord:
        with self._lock:
            if next_state not in RUNTIME_STATES:
                raise InvalidRuntimeTransitionError(f"unknown_target_state:{next_state}")
            allowed = VALID_TRANSITIONS.get(self._state, frozenset())
            if next_state not in allowed:
                raise InvalidRuntimeTransitionError(
                    f"invalid_transition:{self._state}->{next_state}"
                )
            record = TransitionRecord(
                previous_state=self._state,
                next_state=next_state,
                timestamp=utc_now(),
                reason=reason or next_state,
                metadata=dict(metadata or {}),
            )
            self._state = next_state
            self._history.append(record)
            if next_state == "FAILED_SAFE":
                self._failure_reason = reason or "failed_safe"
            return record
