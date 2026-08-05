"""Cross-lifecycle transition mapping (edges between scopes, not a merged FSM)."""
from __future__ import annotations

from typing import Any

# Explicit hand-offs between scopes. These are causal edges, not state equality.
CROSS_SCOPE_TRANSITIONS: tuple[dict[str, str], ...] = (
    {
        "from_scope": "decision",
        "from_states": "APPROVED_SIMULATED",
        "to_scope": "intent",
        "to_states": "DRAFT|SUBMITTED",
        "gate": "decision_approved_simulated",
    },
    {
        "from_scope": "intent",
        "from_states": "ACCEPTED|WORKING",
        "to_scope": "order",
        "to_states": "CREATED|ACCEPTED",
        "gate": "intent_admitted_to_simulator",
    },
    {
        "from_scope": "order",
        "from_states": "PARTIALLY_FILLED|FILLED",
        "to_scope": "position",
        "to_states": "OPENING|OPEN|REDUCING",
        "gate": "fill_applied",
    },
    {
        "from_scope": "position",
        "from_states": "CLOSED|LIQUIDATED_SIMULATED",
        "to_scope": "decision",
        "to_states": "EXITED",
        "gate": "exit_fill_recorded",
    },
    {
        "from_scope": "decision",
        "from_states": "EXITED",
        "to_scope": "reflection",
        "to_states": "PENDING|IN_PROGRESS",
        "gate": "exit_evidence_available",
    },
    {
        "from_scope": "reflection",
        "from_states": "COMPLETE|INCOMPLETE|FAILED_SAFE",
        "to_scope": "decision",
        "to_states": "UNDER_REVIEW|CALIBRATED|CLOSED",
        "gate": "reflection_terminal",
    },
    {
        "from_scope": "session",
        "from_states": "RUNNING|PAUSED|RECOVERING|FINALIZING",
        "to_scope": "decision",
        "to_states": "*",
        "gate": "session_hosts_decisions",
    },
    {
        "from_scope": "session",
        "from_states": "FINALIZING",
        "to_scope": "intent",
        "to_states": "FILLED|CANCELLED|REJECTED|EXPIRED|SUPERSEDED",
        "gate": "session_finalize_requires_resolved_intents",
    },
    {
        "from_scope": "session",
        "from_states": "*",
        "to_scope": "control_plane",
        "to_states": "*",
        "gate": "adapter_only_never_silent_homonym",
    },
)


def transition_mapping_report() -> dict[str, Any]:
    return {
        "schema": "nexus_lifecycle_cross_scope_transitions_v11_1",
        "collapse_to_single_fsm": False,
        "edge_count": len(CROSS_SCOPE_TRANSITIONS),
        "edges": list(CROSS_SCOPE_TRANSITIONS),
        "note": (
            "Edges describe allowed hand-offs between independent lifecycles. "
            "They do not merge state machines or equate homonymous tokens."
        ),
    }
