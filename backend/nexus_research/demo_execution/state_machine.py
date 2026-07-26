"""Demo order execution — order-level state machine.

17 states covering the full order lifecycle from DRAFT through RECONCILED,
including ambiguous and recovery paths.

order_sent is ALWAYS False — SEND_STARTED and ACKNOWLEDGED are defined
for future phases but the adapter blocks actual sending.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False


class DemoOrderState(str, Enum):
    DRAFT = "DRAFT"
    PREFLIGHT_BLOCKED = "PREFLIGHT_BLOCKED"
    READY_FOR_AUTHORIZATION = "READY_FOR_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    SEND_STARTED = "SEND_STARTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    CLOSE_AUTHORIZED = "CLOSE_AUTHORIZED"
    CLOSE_STARTED = "CLOSE_STARTED"
    CLOSED = "CLOSED"
    RECONCILED = "RECONCILED"
    AMBIGUOUS = "AMBIGUOUS"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


TERMINAL_STATES = frozenset({
    DemoOrderState.PREFLIGHT_BLOCKED,
    DemoOrderState.REJECTED,
    DemoOrderState.CANCELLED,
    DemoOrderState.CLOSED,
    DemoOrderState.RECONCILED,
})

BLOCKED_STATES = frozenset({
    DemoOrderState.AMBIGUOUS,
    DemoOrderState.RECOVERY_REQUIRED,
})

_ALLOWED_TRANSITIONS: dict[DemoOrderState, frozenset[DemoOrderState]] = {
    DemoOrderState.DRAFT: frozenset({
        DemoOrderState.PREFLIGHT_BLOCKED,
        DemoOrderState.READY_FOR_AUTHORIZATION,
    }),
    DemoOrderState.PREFLIGHT_BLOCKED: frozenset(),
    DemoOrderState.READY_FOR_AUTHORIZATION: frozenset({
        DemoOrderState.AUTHORIZED,
        DemoOrderState.PREFLIGHT_BLOCKED,
    }),
    DemoOrderState.AUTHORIZED: frozenset({
        DemoOrderState.SEND_STARTED,
        DemoOrderState.REJECTED,
        DemoOrderState.AMBIGUOUS,
    }),
    DemoOrderState.SEND_STARTED: frozenset({
        DemoOrderState.ACKNOWLEDGED,
        DemoOrderState.REJECTED,
        DemoOrderState.AMBIGUOUS,
        DemoOrderState.RECOVERY_REQUIRED,
    }),
    DemoOrderState.ACKNOWLEDGED: frozenset({
        DemoOrderState.PARTIALLY_FILLED,
        DemoOrderState.FILLED,
        DemoOrderState.REJECTED,
        DemoOrderState.CANCEL_PENDING,
        DemoOrderState.AMBIGUOUS,
    }),
    DemoOrderState.PARTIALLY_FILLED: frozenset({
        DemoOrderState.FILLED,
        DemoOrderState.CANCEL_PENDING,
        DemoOrderState.AMBIGUOUS,
        DemoOrderState.CLOSE_AUTHORIZED,
    }),
    DemoOrderState.FILLED: frozenset({
        DemoOrderState.CLOSE_AUTHORIZED,
        DemoOrderState.RECONCILED,
        DemoOrderState.AMBIGUOUS,
    }),
    DemoOrderState.REJECTED: frozenset({
        DemoOrderState.RECONCILED,
    }),
    DemoOrderState.CANCEL_PENDING: frozenset({
        DemoOrderState.CANCELLED,
        DemoOrderState.AMBIGUOUS,
        DemoOrderState.RECOVERY_REQUIRED,
    }),
    DemoOrderState.CANCELLED: frozenset({
        DemoOrderState.RECONCILED,
    }),
    DemoOrderState.CLOSE_AUTHORIZED: frozenset({
        DemoOrderState.CLOSE_STARTED,
        DemoOrderState.AMBIGUOUS,
    }),
    DemoOrderState.CLOSE_STARTED: frozenset({
        DemoOrderState.CLOSED,
        DemoOrderState.AMBIGUOUS,
        DemoOrderState.RECOVERY_REQUIRED,
    }),
    DemoOrderState.CLOSED: frozenset({
        DemoOrderState.RECONCILED,
    }),
    DemoOrderState.RECONCILED: frozenset(),
    DemoOrderState.AMBIGUOUS: frozenset({
        DemoOrderState.RECOVERY_REQUIRED,
        DemoOrderState.RECONCILED,
        DemoOrderState.ACKNOWLEDGED,
        DemoOrderState.REJECTED,
        DemoOrderState.CANCELLED,
    }),
    DemoOrderState.RECOVERY_REQUIRED: frozenset({
        DemoOrderState.AMBIGUOUS,
        DemoOrderState.RECONCILED,
    }),
}


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    timestamp_ms: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_state,
            "to": self.to_state,
            "timestampMs": self.timestamp_ms,
            "reason": self.reason,
        }


@dataclass
class DemoOrderStateMachine:
    """Per-order state machine. order_sent is NEVER True."""

    state: DemoOrderState = DemoOrderState.DRAFT
    history: list[StateTransition] = field(default_factory=list)
    order_sent: bool = field(default=False, init=False)

    def transition(self, target: DemoOrderState | str, *, reason: str = "") -> DemoOrderState:
        if isinstance(target, str):
            target = DemoOrderState(target)

        allowed = _ALLOWED_TRANSITIONS.get(self.state, frozenset())
        if target not in allowed:
            raise ValueError(
                f"illegal_transition:{self.state.value}->{target.value} "
                f"(allowed: {', '.join(s.value for s in allowed) or 'none'})"
            )

        self.history.append(StateTransition(
            from_state=self.state.value,
            to_state=target.value,
            timestamp_ms=int(time.time() * 1000),
            reason=reason,
        ))
        self.state = target
        return self.state

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def is_blocked(self) -> bool:
        return self.state in BLOCKED_STATES

    @property
    def can_send(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "isTerminal": self.is_terminal,
            "isBlocked": self.is_blocked,
            "canSend": False,
            "orderSent": False,
            "history": [t.to_dict() for t in self.history],
        }
