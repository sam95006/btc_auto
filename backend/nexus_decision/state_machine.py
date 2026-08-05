"""Fail-closed Decision Lifecycle state machine V11."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


CANONICAL_STATES: tuple[str, ...] = (
    "OBSERVED",
    "UNDERSTANDING",
    "CHALLENGED",
    "RISK_REVIEWED",
    "APPROVED_SIMULATED",
    "REJECTED",
    "MONITORING",
    "EXITED",
    "UNDER_REVIEW",
    "CALIBRATED",
    "CLOSED",
    "BLOCKED_AMBIGUOUS",
)

TERMINAL_STATES: frozenset[str] = frozenset({"CLOSED"})

# Observe→Understand→Challenge→Decide→Record→Monitor→Review→Calibrate→Improve
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "OBSERVED": frozenset({"UNDERSTANDING", "REJECTED", "BLOCKED_AMBIGUOUS"}),
    "UNDERSTANDING": frozenset({"CHALLENGED", "REJECTED", "BLOCKED_AMBIGUOUS"}),
    "CHALLENGED": frozenset({"RISK_REVIEWED", "REJECTED", "BLOCKED_AMBIGUOUS"}),
    "RISK_REVIEWED": frozenset(
        {"APPROVED_SIMULATED", "REJECTED", "BLOCKED_AMBIGUOUS"}
    ),
    "APPROVED_SIMULATED": frozenset({"MONITORING", "BLOCKED_AMBIGUOUS"}),
    "MONITORING": frozenset({"EXITED", "UNDER_REVIEW", "BLOCKED_AMBIGUOUS"}),
    "EXITED": frozenset({"UNDER_REVIEW", "CLOSED", "BLOCKED_AMBIGUOUS"}),
    "UNDER_REVIEW": frozenset({"CALIBRATED", "CLOSED", "BLOCKED_AMBIGUOUS"}),
    "CALIBRATED": frozenset({"CLOSED"}),
    "REJECTED": frozenset({"UNDER_REVIEW", "CLOSED"}),
    "BLOCKED_AMBIGUOUS": frozenset({"CLOSED"}),
    "CLOSED": frozenset(),
}


class InvalidTransitionError(Exception):
    """Illegal Decision Lifecycle transition — fail closed, no silent mutation."""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class TransitionRecord:
    previous_state: str
    next_state: str
    timestamp: str
    reason: str
    stage: str
    idempotency_key: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_state": self.previous_state,
            "next_state": self.next_state,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "stage": self.stage,
            "idempotency_key": self.idempotency_key,
            "metadata": dict(self.metadata),
        }


class DecisionStateMachine:
    """Thread-safe fail-closed lifecycle for one Decision Object."""

    def __init__(self, *, initial: str = "OBSERVED") -> None:
        if initial not in CANONICAL_STATES:
            raise InvalidTransitionError(f"unknown_initial_state:{initial}")
        self._lock = threading.RLock()
        self._state = initial
        self._history: list[TransitionRecord] = []
        self._seen_keys: set[str] = set()

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

    def restore(self, state: str, history: list[dict[str, Any]] | None = None) -> None:
        """Restore from checkpoint. Unknown states fail closed."""
        with self._lock:
            if state not in CANONICAL_STATES:
                raise InvalidTransitionError(f"unknown_restore_state:{state}")
            self._state = state
            self._history = []
            self._seen_keys = set()
            for item in history or []:
                key = str(item.get("idempotency_key") or "")
                if key:
                    self._seen_keys.add(key)
                self._history.append(
                    TransitionRecord(
                        previous_state=str(item.get("previous_state") or ""),
                        next_state=str(item.get("next_state") or ""),
                        timestamp=str(item.get("timestamp") or ""),
                        reason=str(item.get("reason") or ""),
                        stage=str(item.get("stage") or ""),
                        idempotency_key=key,
                        metadata=dict(item.get("metadata") or {}),
                    )
                )

    def transition(
        self,
        next_state: str,
        *,
        stage: str,
        reason: str = "",
        idempotency_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> TransitionRecord:
        with self._lock:
            if not idempotency_key:
                raise InvalidTransitionError("idempotency_key_required")
            if idempotency_key in self._seen_keys:
                # Idempotent replay: return last matching record without mutation.
                for rec in reversed(self._history):
                    if rec.idempotency_key == idempotency_key:
                        if rec.next_state != next_state:
                            raise InvalidTransitionError(
                                f"idempotency_conflict:{idempotency_key}:"
                                f"{rec.next_state}!={next_state}"
                            )
                        return rec
                raise InvalidTransitionError(f"idempotency_orphan:{idempotency_key}")
            if next_state not in CANONICAL_STATES:
                raise InvalidTransitionError(f"unknown_target_state:{next_state}")
            allowed = VALID_TRANSITIONS.get(self._state, frozenset())
            if next_state not in allowed:
                raise InvalidTransitionError(
                    f"invalid_transition:{self._state}->{next_state}:stage={stage}"
                )
            record = TransitionRecord(
                previous_state=self._state,
                next_state=next_state,
                timestamp=_utc(),
                reason=reason or stage,
                stage=stage,
                idempotency_key=idempotency_key,
                metadata=dict(metadata or {}),
            )
            self._state = next_state
            self._history.append(record)
            self._seen_keys.add(idempotency_key)
            return record
