"""Canonical lifecycle ontology — scoped authorities, not a single FSM."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.nexus_autonomy.session_state_machine import (
    CANONICAL_STATES as SESSION_STATES,
    TERMINAL_STATES as SESSION_TERMINALS,
    VALID_TRANSITIONS as SESSION_TRANSITIONS,
)
from backend.nexus_decision.state_machine import (
    CANONICAL_STATES as DECISION_STATES,
    TERMINAL_STATES as DECISION_TERMINALS,
    VALID_TRANSITIONS as DECISION_TRANSITIONS,
)
from backend.nexus_execution.contracts import (
    ORDER_STATES,
    ORDER_TRANSITIONS,
    POSITION_STATES,
    POSITION_TRANSITIONS,
)
from backend.nexus_private_control.state_machine import (
    CANONICAL_STATES as CONTROL_STATES,
    TERMINAL_STATES as CONTROL_TERMINALS,
    VALID_TRANSITIONS as CONTROL_TRANSITIONS,
)

ONTOLOGY_SCHEMA = "nexus_lifecycle_ontology_v11_1"
ONTOLOGY_VERSION = "v11.1.lifecycle_vocabulary.1"

# Intent is a first-class Private Core scope sitting between Decision approval
# and Order admission. It was previously informal in the closed-loop harness.
INTENT_STATES: tuple[str, ...] = (
    "DRAFT",
    "SUBMITTED",
    "ACCEPTED",
    "WORKING",
    "PARTIAL",
    "FILLED",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
    "SUPERSEDED",
    "BLOCKED_AMBIGUOUS",
)
INTENT_TERMINALS: frozenset[str] = frozenset(
    {"FILLED", "CANCELLED", "REJECTED", "EXPIRED", "SUPERSEDED"}
)
INTENT_UNRESOLVED: frozenset[str] = frozenset(
    {"DRAFT", "SUBMITTED", "ACCEPTED", "WORKING", "PARTIAL", "BLOCKED_AMBIGUOUS"}
)
INTENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"SUBMITTED", "CANCELLED", "REJECTED", "BLOCKED_AMBIGUOUS"}),
    "SUBMITTED": frozenset({"ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED", "BLOCKED_AMBIGUOUS"}),
    "ACCEPTED": frozenset({"WORKING", "CANCELLED", "REJECTED", "EXPIRED", "BLOCKED_AMBIGUOUS"}),
    "WORKING": frozenset({"PARTIAL", "FILLED", "CANCELLED", "EXPIRED", "BLOCKED_AMBIGUOUS"}),
    "PARTIAL": frozenset({"PARTIAL", "FILLED", "CANCELLED", "EXPIRED", "BLOCKED_AMBIGUOUS"}),
    "FILLED": frozenset(),
    "CANCELLED": frozenset(),
    "REJECTED": frozenset(),
    "EXPIRED": frozenset(),
    "SUPERSEDED": frozenset(),
    "BLOCKED_AMBIGUOUS": frozenset({"CANCELLED", "SUPERSEDED"}),
}

# Reflection is independent of Decision/Session FSMs. COMPLETE requires exit evidence.
REFLECTION_STATES: tuple[str, ...] = (
    "PENDING",
    "IN_PROGRESS",
    "AWAITING_EXIT_EVIDENCE",
    "COMPLETE",
    "INCOMPLETE",
    "BLOCKED_AMBIGUOUS",
    "FAILED_SAFE",
)
REFLECTION_TERMINALS: frozenset[str] = frozenset(
    {"COMPLETE", "INCOMPLETE", "FAILED_SAFE"}
)
REFLECTION_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"IN_PROGRESS", "AWAITING_EXIT_EVIDENCE", "FAILED_SAFE", "BLOCKED_AMBIGUOUS"}),
    "IN_PROGRESS": frozenset(
        {"AWAITING_EXIT_EVIDENCE", "COMPLETE", "INCOMPLETE", "FAILED_SAFE", "BLOCKED_AMBIGUOUS"}
    ),
    "AWAITING_EXIT_EVIDENCE": frozenset(
        {"IN_PROGRESS", "COMPLETE", "INCOMPLETE", "FAILED_SAFE", "BLOCKED_AMBIGUOUS"}
    ),
    "COMPLETE": frozenset(),
    "INCOMPLETE": frozenset(),
    "BLOCKED_AMBIGUOUS": frozenset({"INCOMPLETE", "FAILED_SAFE"}),
    "FAILED_SAFE": frozenset(),
}

ORDER_TERMINALS: frozenset[str] = frozenset(
    {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
)
POSITION_TERMINALS: frozenset[str] = frozenset(
    {"CLOSED", "LIQUIDATED_SIMULATED", "NONE"}
)
POSITION_OPEN_LIKE: frozenset[str] = frozenset({"OPENING", "OPEN", "REDUCING"})


@dataclass(frozen=True)
class LifecycleScope:
    """One scoped lifecycle authority (never merge scopes)."""

    scope_id: str
    display_name: str
    owner_module: str
    states: tuple[str, ...]
    terminals: frozenset[str]
    transitions: dict[str, frozenset[str]] | frozenset[tuple[str, str]]
    role: str  # trading_loop | process_control | evidence
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        transitions: Any
        if isinstance(self.transitions, frozenset):
            transitions = sorted([list(t) for t in self.transitions])
        else:
            transitions = {k: sorted(v) for k, v in self.transitions.items()}
        return {
            "scope_id": self.scope_id,
            "display_name": self.display_name,
            "owner_module": self.owner_module,
            "states": list(self.states),
            "terminals": sorted(self.terminals),
            "transitions": transitions,
            "role": self.role,
            "notes": self.notes,
        }


def _order_transition_map() -> dict[str, frozenset[str]]:
    out: dict[str, set[str]] = {s: set() for s in ORDER_STATES}
    for a, b in ORDER_TRANSITIONS:
        out.setdefault(a, set()).add(b)
    return {k: frozenset(v) for k, v in out.items()}


def _position_transition_map() -> dict[str, frozenset[str]]:
    out: dict[str, set[str]] = {s: set() for s in POSITION_STATES}
    for a, b in POSITION_TRANSITIONS:
        out.setdefault(a, set()).add(b)
    return {k: frozenset(v) for k, v in out.items()}


LIFECYCLE_SCOPES: tuple[LifecycleScope, ...] = (
    LifecycleScope(
        scope_id="decision",
        display_name="Decision",
        owner_module="backend.nexus_decision.state_machine",
        states=DECISION_STATES,
        terminals=DECISION_TERMINALS,
        transitions=DECISION_TRANSITIONS,
        role="trading_loop",
        notes="Observe→…→CLOSED. BLOCKED_AMBIGUOUS is adjudicated before CLOSED.",
    ),
    LifecycleScope(
        scope_id="session",
        display_name="Session",
        owner_module="backend.nexus_autonomy.session_state_machine",
        states=SESSION_STATES,
        terminals=SESSION_TERMINALS,
        transitions=SESSION_TRANSITIONS,
        role="trading_loop",
        notes="Session orchestration authority for Private Core simulated sessions.",
    ),
    LifecycleScope(
        scope_id="intent",
        display_name="Intent",
        owner_module="backend.nexus_contracts.lifecycle.ontology",
        states=INTENT_STATES,
        terminals=INTENT_TERMINALS,
        transitions=INTENT_TRANSITIONS,
        role="trading_loop",
        notes="OrderIntent lifecycle between Decision approval and Order admission.",
    ),
    LifecycleScope(
        scope_id="order",
        display_name="Order",
        owner_module="backend.nexus_execution.contracts",
        states=tuple(sorted(ORDER_STATES)),
        terminals=ORDER_TERMINALS,
        transitions=_order_transition_map(),
        role="trading_loop",
        notes="Simulated order states from execution_contract_v1_1.",
    ),
    LifecycleScope(
        scope_id="position",
        display_name="Position",
        owner_module="backend.nexus_execution.contracts",
        states=tuple(sorted(POSITION_STATES)),
        terminals=POSITION_TERMINALS,
        transitions=_position_transition_map(),
        role="trading_loop",
        notes="Simulated position states; CLOSED forbids residual qty > 0.",
    ),
    LifecycleScope(
        scope_id="reflection",
        display_name="Reflection",
        owner_module="backend.nexus_contracts.lifecycle.ontology",
        states=REFLECTION_STATES,
        terminals=REFLECTION_TERMINALS,
        transitions=REFLECTION_TRANSITIONS,
        role="trading_loop",
        notes="COMPLETE requires exit evidence; never before Decision EXITED/CLOSED path.",
    ),
    LifecycleScope(
        scope_id="control_plane",
        display_name="ControlPlane",
        owner_module="backend.nexus_private_control.state_machine",
        states=CONTROL_STATES,
        terminals=CONTROL_TERMINALS,
        transitions=CONTROL_TRANSITIONS,
        role="process_control",
        notes=(
            "Founder process-control lifecycle. Homonymous tokens with Session "
            "(RUNNING/PAUSED/RECOVERING/FAILED_SAFE) are NOT identical; adapter required."
        ),
    ),
)


def build_ontology() -> dict[str, Any]:
    scopes = [s.to_dict() for s in LIFECYCLE_SCOPES]
    by_id = {s["scope_id"]: s for s in scopes}
    return {
        "schema": ONTOLOGY_SCHEMA,
        "version": ONTOLOGY_VERSION,
        "policy": {
            "collapse_to_single_fsm": False,
            "silent_homonym_mapping": False,
            "mass_delete_competitors": False,
            "exchange_write": False,
            "mainnet": False,
            "real_money": False,
        },
        "trading_loop_scopes": [
            s.scope_id for s in LIFECYCLE_SCOPES if s.role == "trading_loop"
        ],
        "process_control_scopes": [
            s.scope_id for s in LIFECYCLE_SCOPES if s.role == "process_control"
        ],
        "scopes": scopes,
        "by_scope": by_id,
        "intent_unresolved_states": sorted(INTENT_UNRESOLVED),
        "position_open_like_states": sorted(POSITION_OPEN_LIKE),
        "homonym_tokens_session_control": sorted(
            set(SESSION_STATES) & set(CONTROL_STATES)
        ),
    }
