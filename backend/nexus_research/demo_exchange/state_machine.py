"""Phase 6.6 — Execution state machine SKELETON only (no exchange write states)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DemoState(str, Enum):
    DEMO_DISABLED = "DEMO_DISABLED"
    READ_ONLY = "READ_ONLY"
    RECONCILING = "RECONCILING"
    RECONCILED = "RECONCILED"
    MISMATCH = "MISMATCH"
    WRITE_LOCKED = "WRITE_LOCKED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


# Explicitly excluded — never add states that imply exchange write:
FORBIDDEN_STATES = frozenset({"ORDER_PENDING", "ORDER_SENT", "FILLED"})

_ALLOWED_TRANSITIONS: dict[DemoState, frozenset[DemoState]] = {
    DemoState.DEMO_DISABLED: frozenset({DemoState.READ_ONLY}),
    DemoState.READ_ONLY: frozenset(
        {DemoState.RECONCILING, DemoState.WRITE_LOCKED, DemoState.DEMO_DISABLED}
    ),
    DemoState.RECONCILING: frozenset(
        {DemoState.RECONCILED, DemoState.MISMATCH, DemoState.RECOVERY_REQUIRED}
    ),
    DemoState.RECONCILED: frozenset(
        {DemoState.READ_ONLY, DemoState.RECONCILING, DemoState.WRITE_LOCKED}
    ),
    DemoState.MISMATCH: frozenset(
        {DemoState.WRITE_LOCKED, DemoState.RECOVERY_REQUIRED, DemoState.RECONCILING}
    ),
    DemoState.WRITE_LOCKED: frozenset(
        {DemoState.RECOVERY_REQUIRED, DemoState.READ_ONLY, DemoState.DEMO_DISABLED}
    ),
    DemoState.RECOVERY_REQUIRED: frozenset(
        {DemoState.RECONCILING, DemoState.WRITE_LOCKED, DemoState.DEMO_DISABLED}
    ),
}


@dataclass
class DemoStateMachine:
    """Skeleton only — never calls exchange write APIs."""

    state: DemoState = DemoState.DEMO_DISABLED
    history: list[str] = field(default_factory=list)
    write_calls: int = 0  # must remain 0

    def transition(self, target: DemoState | str) -> DemoState:
        if isinstance(target, str):
            if target in FORBIDDEN_STATES:
                raise ValueError(f"forbidden_state:{target}")
            target = DemoState(target)
        if target.value in FORBIDDEN_STATES:
            raise ValueError(f"forbidden_state:{target.value}")
        allowed = _ALLOWED_TRANSITIONS.get(self.state, frozenset())
        if target not in allowed:
            raise ValueError(f"illegal_transition:{self.state.value}->{target.value}")
        self.history.append(f"{self.state.value}->{target.value}")
        self.state = target
        if target in {DemoState.MISMATCH, DemoState.WRITE_LOCKED, DemoState.RECOVERY_REQUIRED}:
            # fail-closed posture
            pass
        return self.state

    def enable_read_only(self) -> DemoState:
        if self.state == DemoState.DEMO_DISABLED:
            return self.transition(DemoState.READ_ONLY)
        return self.state

    def begin_reconcile(self) -> DemoState:
        if self.state == DemoState.READ_ONLY:
            return self.transition(DemoState.RECONCILING)
        if self.state == DemoState.RECONCILED:
            return self.transition(DemoState.RECONCILING)
        raise ValueError(f"cannot_reconcile_from:{self.state.value}")

    def complete_reconcile(self, *, ok: bool) -> DemoState:
        if self.state != DemoState.RECONCILING:
            raise ValueError("not_reconciling")
        return self.transition(DemoState.RECONCILED if ok else DemoState.MISMATCH)

    def lock_writes(self) -> DemoState:
        if self.state in {
            DemoState.READ_ONLY,
            DemoState.RECONCILED,
            DemoState.MISMATCH,
            DemoState.RECOVERY_REQUIRED,
        }:
            return self.transition(DemoState.WRITE_LOCKED)
        if self.state == DemoState.WRITE_LOCKED:
            return self.state
        raise ValueError(f"cannot_lock_from:{self.state.value}")

    def summary(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "history": list(self.history),
            "writeCalls": self.write_calls,
            "forbiddenStatesAbsent": True,
            "allowedStates": [s.value for s in DemoState],
        }
