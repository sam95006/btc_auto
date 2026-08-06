"""Fail-closed Shadow Decision lifecycle state machine."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_shadow_decision_ledger.constants import (
    LIFECYCLE_STATES,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
)
from backend.nexus_shadow_decision_ledger.contracts import ShadowDecisionRecord, utc_now


class InvalidShadowTransitionError(Exception):
    """Illegal Shadow Decision lifecycle transition — fail closed."""


@dataclass
class TransitionRecord:
    previous_state: str
    next_state: str
    timestamp: str
    reason: str
    idempotency_key: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_state": self.previous_state,
            "next_state": self.next_state,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "idempotency_key": self.idempotency_key,
            "metadata": dict(self.metadata),
        }


class ShadowDecisionLifecycle:
    """Thread-safe fail-closed lifecycle for one Shadow Decision record."""

    def __init__(self, record: ShadowDecisionRecord) -> None:
        if record.lifecycle_state not in LIFECYCLE_STATES:
            raise InvalidShadowTransitionError(
                f"unknown_initial_state:{record.lifecycle_state}"
            )
        self._lock = threading.RLock()
        self.record = record
        self._seen_keys: set[str] = {
            str(h.get("idempotency_key") or "")
            for h in record.transition_history
            if h.get("idempotency_key")
        }

    @property
    def state(self) -> str:
        with self._lock:
            return self.record.lifecycle_state

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def transition(
        self,
        next_state: str,
        *,
        reason: str = "",
        idempotency_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> TransitionRecord:
        with self._lock:
            if self.record.sealed:
                raise InvalidShadowTransitionError("sealed_record_immutable")
            if not idempotency_key:
                raise InvalidShadowTransitionError("idempotency_key_required")
            if idempotency_key in self._seen_keys:
                for item in reversed(self.record.transition_history):
                    if item.get("idempotency_key") == idempotency_key:
                        if item.get("next_state") != next_state:
                            raise InvalidShadowTransitionError(
                                f"idempotency_conflict:{idempotency_key}"
                            )
                        return TransitionRecord(
                            previous_state=str(item.get("previous_state") or ""),
                            next_state=str(item.get("next_state") or ""),
                            timestamp=str(item.get("timestamp") or ""),
                            reason=str(item.get("reason") or ""),
                            idempotency_key=idempotency_key,
                            metadata=dict(item.get("metadata") or {}),
                        )
                raise InvalidShadowTransitionError(f"idempotency_orphan:{idempotency_key}")
            if next_state not in LIFECYCLE_STATES:
                raise InvalidShadowTransitionError(f"unknown_target_state:{next_state}")
            allowed = VALID_TRANSITIONS.get(self.record.lifecycle_state, frozenset())
            if next_state not in allowed:
                raise InvalidShadowTransitionError(
                    f"invalid_transition:{self.record.lifecycle_state}->{next_state}"
                )
            prev = self.record.lifecycle_state
            rec = TransitionRecord(
                previous_state=prev,
                next_state=next_state,
                timestamp=utc_now(),
                reason=reason or next_state,
                idempotency_key=idempotency_key,
                metadata=dict(metadata or {}),
            )
            self.record.lifecycle_state = next_state
            self.record.updated_at = rec.timestamp
            self.record.transition_history.append(rec.to_dict())
            self._seen_keys.add(idempotency_key)

            # SHADOW_OPENED means an internal virtual research position ONLY.
            if next_state == "SHADOW_OPENED":
                self.record.virtual_research_position = True
                self.record.actual_ordered = False
                self.record.actual_filled = False
                self.record.exchange_order_id = None
            return rec

    def advance_full_happy_path(self, *, prefix: str = "hp") -> None:
        """Advance OBSERVED → REFLECTED for fixture/integration tests."""
        path = [
            "CANDIDATE",
            "REVIEWED",
            "SHADOW_READY",
            "SHADOW_OPENED",
            "SHADOW_MANAGING",
            "SHADOW_CLOSED",
            "OUTCOME_PENDING",
            "OUTCOME_RECORDED",
            "REFLECTION_PENDING",
            "REFLECTED",
        ]
        for i, nxt in enumerate(path):
            self.transition(nxt, reason=f"happy_path:{nxt}", idempotency_key=f"{prefix}:{i}:{nxt}")
