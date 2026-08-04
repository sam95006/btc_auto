"""NEXUS Autonomous Session State Machine V1.1 — canonical fail-closed lifecycle.

Every session transition is recorded with:
  event_id, previous_state, next_state, timestamp, reason,
  checkpoint_id, ledger_sequence, idempotency_key

Invalid transitions must FAIL CLOSED (raise or return REJECTED). No silent state
mutation is permitted.

Canonical states:
  CREATED, INITIALIZING, RUNNING, PAUSING, PAUSED,
  RECOVERING, FINALIZING, COMPLETED, BLOCKED, FAILED_SAFE

Terminal states: COMPLETED, BLOCKED, FAILED_SAFE

This module is Founder-only orchestration metadata. It never places orders and
never writes to any exchange endpoint. It never logs secrets.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable


CANONICAL_STATES: tuple[str, ...] = (
    "CREATED",
    "INITIALIZING",
    "RUNNING",
    "PAUSING",
    "PAUSED",
    "RECOVERING",
    "FINALIZING",
    "COMPLETED",
    "BLOCKED",
    "FAILED_SAFE",
)

TERMINAL_STATES: frozenset[str] = frozenset({"COMPLETED", "BLOCKED", "FAILED_SAFE"})

# Every entry (a, {b, c}) means: from state `a`, allowed next states are {b, c}.
# Anything not listed is an INVALID transition and must fail closed.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"INITIALIZING", "FAILED_SAFE", "BLOCKED"}),
    "INITIALIZING": frozenset({"RUNNING", "FAILED_SAFE", "BLOCKED"}),
    "RUNNING": frozenset({"PAUSING", "FINALIZING", "RECOVERING", "BLOCKED", "FAILED_SAFE"}),
    "PAUSING": frozenset({"PAUSED", "FAILED_SAFE", "BLOCKED"}),
    "PAUSED": frozenset({"RUNNING", "RECOVERING", "FINALIZING", "BLOCKED", "FAILED_SAFE"}),
    "RECOVERING": frozenset({"RUNNING", "BLOCKED", "FAILED_SAFE", "FINALIZING"}),
    "FINALIZING": frozenset({"COMPLETED", "BLOCKED", "FAILED_SAFE"}),
    # Terminal states have no outgoing transitions.
    "COMPLETED": frozenset(),
    "BLOCKED": frozenset(),
    "FAILED_SAFE": frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when an illegal state transition is attempted. Fail-closed."""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TransitionRecord:
    event_id: str
    session_id: str
    previous_state: str
    next_state: str
    timestamp: str
    reason: str
    checkpoint_id: str | None
    ledger_sequence: int | None
    idempotency_key: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "previous_state": self.previous_state,
            "next_state": self.next_state,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "checkpoint_id": self.checkpoint_id,
            "ledger_sequence": self.ledger_sequence,
            "idempotency_key": self.idempotency_key,
            "metadata": _sanitize_metadata(self.metadata),
        }


_SECRET_LIKE_KEYS = {
    "api_key",
    "api_secret",
    "secret",
    "password",
    "token",
    "authorization",
    "private_key",
    "bearer",
}


def _sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Drop any secret-like keys/values. Fails closed by omission (never partial)."""
    safe: dict[str, Any] = {}
    for k, v in meta.items():
        kl = str(k).lower()
        if any(bad in kl for bad in _SECRET_LIKE_KEYS):
            continue
        if isinstance(v, str) and any(bad in v.lower() for bad in _SECRET_LIKE_KEYS):
            continue
        safe[k] = v
    return safe


class SessionStateMachine:
    """Founder-only canonical session state machine.

    Thread-safe. Every transition is validated against `VALID_TRANSITIONS`.
    Duplicate idempotency keys are treated as no-ops (returning the recorded
    transition), preventing double-transition races from concurrency injection.
    """

    def __init__(self, session_id: str) -> None:
        if not session_id or not isinstance(session_id, str):
            raise ValueError("session_id_required")
        self.session_id = session_id
        self._state: str = "CREATED"
        self._history: list[TransitionRecord] = []
        self._by_idempotency: dict[str, TransitionRecord] = {}
        self._invalid_attempts: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

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

    def invalid_attempts(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._invalid_attempts)

    def invalid_attempt_count(self) -> int:
        with self._lock:
            return len(self._invalid_attempts)

    # ------------------------------------------------------------------
    # Transition core
    # ------------------------------------------------------------------

    def can_transition(self, next_state: str) -> bool:
        with self._lock:
            allowed = VALID_TRANSITIONS.get(self._state, frozenset())
            return next_state in allowed

    def transition(
        self,
        next_state: str,
        *,
        reason: str,
        idempotency_key: str,
        checkpoint_id: str | None = None,
        ledger_sequence: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TransitionRecord:
        """Apply a state transition. Fails closed on invalid transition.

        Idempotent: repeated calls with the same idempotency_key return the
        original TransitionRecord without mutating history.
        """
        if next_state not in CANONICAL_STATES:
            raise InvalidTransitionError(f"unknown_state:{next_state}")
        if not idempotency_key:
            raise InvalidTransitionError("idempotency_key_required")
        if not reason:
            raise InvalidTransitionError("reason_required")

        with self._lock:
            existing = self._by_idempotency.get(idempotency_key)
            if existing is not None:
                # Idempotent replay — only accept if the requested target matches.
                if existing.next_state != next_state:
                    self._invalid_attempts.append(
                        {
                            "reason": "idempotency_key_conflict",
                            "idempotency_key": idempotency_key,
                            "requested_next_state": next_state,
                            "existing_next_state": existing.next_state,
                            "timestamp": _utc(),
                        }
                    )
                    raise InvalidTransitionError(
                        f"idempotency_conflict:{idempotency_key}"
                    )
                return existing

            prev = self._state
            allowed = VALID_TRANSITIONS.get(prev, frozenset())
            if next_state not in allowed:
                self._invalid_attempts.append(
                    {
                        "reason": "invalid_transition",
                        "previous_state": prev,
                        "requested_next_state": next_state,
                        "attempted_reason": reason,
                        "idempotency_key": idempotency_key,
                        "timestamp": _utc(),
                    }
                )
                raise InvalidTransitionError(
                    f"invalid_transition:{prev}->{next_state}"
                )

            ts = _utc()
            material = "|".join(
                [
                    self.session_id,
                    prev,
                    next_state,
                    ts,
                    reason,
                    str(checkpoint_id or ""),
                    str(ledger_sequence or ""),
                    idempotency_key,
                    str(time.time_ns()),
                ]
            )
            event_id = _sha(material)[:32]
            record = TransitionRecord(
                event_id=event_id,
                session_id=self.session_id,
                previous_state=prev,
                next_state=next_state,
                timestamp=ts,
                reason=reason,
                checkpoint_id=checkpoint_id,
                ledger_sequence=ledger_sequence,
                idempotency_key=idempotency_key,
                metadata=_sanitize_metadata(metadata or {}),
            )
            self._history.append(record)
            self._by_idempotency[idempotency_key] = record
            self._state = next_state
            return record

    def force_failed_safe(
        self,
        *,
        reason: str,
        idempotency_key: str,
        checkpoint_id: str | None = None,
        ledger_sequence: int | None = None,
    ) -> TransitionRecord:
        """Force session into FAILED_SAFE. Always legal unless already terminal.

        If already terminal (COMPLETED/BLOCKED/FAILED_SAFE), the existing state
        is preserved and an invalid_attempt is logged (never overwrite terminal).
        """
        with self._lock:
            if self._state in TERMINAL_STATES:
                self._invalid_attempts.append(
                    {
                        "reason": "force_failed_safe_after_terminal",
                        "current_state": self._state,
                        "idempotency_key": idempotency_key,
                        "timestamp": _utc(),
                    }
                )
                return self._history[-1] if self._history else TransitionRecord(
                    event_id="terminal",
                    session_id=self.session_id,
                    previous_state=self._state,
                    next_state=self._state,
                    timestamp=_utc(),
                    reason="already_terminal",
                    checkpoint_id=checkpoint_id,
                    ledger_sequence=ledger_sequence,
                    idempotency_key=idempotency_key,
                )
            # Direct forced transition — bypasses VALID_TRANSITIONS.
            prev = self._state
            ts = _utc()
            material = "|".join(
                [
                    self.session_id,
                    prev,
                    "FAILED_SAFE",
                    ts,
                    reason,
                    str(checkpoint_id or ""),
                    str(ledger_sequence or ""),
                    idempotency_key,
                    str(time.time_ns()),
                ]
            )
            event_id = _sha(material)[:32]
            record = TransitionRecord(
                event_id=event_id,
                session_id=self.session_id,
                previous_state=prev,
                next_state="FAILED_SAFE",
                timestamp=ts,
                reason=reason,
                checkpoint_id=checkpoint_id,
                ledger_sequence=ledger_sequence,
                idempotency_key=idempotency_key,
                metadata={"forced": True},
            )
            self._history.append(record)
            self._by_idempotency[idempotency_key] = record
            self._state = "FAILED_SAFE"
            return record

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def serialize(self) -> dict[str, Any]:
        with self._lock:
            return {
                "session_id": self.session_id,
                "state": self._state,
                "history": [r.to_dict() for r in self._history],
                "invalid_attempts": list(self._invalid_attempts),
                "is_terminal": self._state in TERMINAL_STATES,
                "schema": "session_state_machine_v1_1",
            }

    @classmethod
    def restore(cls, blob: dict[str, Any]) -> "SessionStateMachine":
        if blob.get("schema") != "session_state_machine_v1_1":
            raise ValueError("unknown_state_machine_schema")
        sm = cls(session_id=str(blob["session_id"]))
        history = blob.get("history") or []
        # Rehydrate history without re-validating transitions (the persisted
        # history was already validated when produced).
        for h in history:
            rec = TransitionRecord(
                event_id=str(h["event_id"]),
                session_id=str(h["session_id"]),
                previous_state=str(h["previous_state"]),
                next_state=str(h["next_state"]),
                timestamp=str(h["timestamp"]),
                reason=str(h["reason"]),
                checkpoint_id=h.get("checkpoint_id"),
                ledger_sequence=h.get("ledger_sequence"),
                idempotency_key=str(h["idempotency_key"]),
                metadata=dict(h.get("metadata") or {}),
            )
            sm._history.append(rec)
            sm._by_idempotency[rec.idempotency_key] = rec
        sm._state = str(blob.get("state") or (sm._history[-1].next_state if sm._history else "CREATED"))
        sm._invalid_attempts = list(blob.get("invalid_attempts") or [])
        return sm


def is_valid_transition(prev: str, nxt: str) -> bool:
    return nxt in VALID_TRANSITIONS.get(prev, frozenset())


def transition_table() -> dict[str, list[str]]:
    return {k: sorted(v) for k, v in VALID_TRANSITIONS.items()}


def summarize_history(sm: SessionStateMachine) -> dict[str, Any]:
    hist = sm.history()
    by_next: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    for h in hist:
        by_next[h["next_state"]] = by_next.get(h["next_state"], 0) + 1
        by_reason[h["reason"]] = by_reason.get(h["reason"], 0) + 1
    return {
        "session_id": sm.session_id,
        "final_state": sm.state,
        "terminal": sm.is_terminal,
        "transition_count": len(hist),
        "transitions_by_next_state": by_next,
        "transitions_by_reason": by_reason,
        "invalid_attempt_count": sm.invalid_attempt_count(),
    }
