"""Decision vs Execution / Position / Order vocabulary mismatch analysis."""
from __future__ import annotations

from typing import Any

from tools.review.r1_decision_execution.lane_loader import LaneImportContext, LaneRoots, resolve_lane_roots


# Incompatible pairs that must never co-exist once a real bridge exists.
FORBIDDEN_COMBINATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("decision", "CLOSED", "position", "OPEN"),
    ("decision", "CLOSED", "position", "OPENING"),
    ("decision", "CLOSED", "position", "REDUCING"),
    ("decision", "MONITORING", "position", "CLOSED"),
    ("decision", "MONITORING", "position", "NONE"),
    ("decision", "APPROVED_SIMULATED", "position", "OPEN"),
    ("decision", "OBSERVED", "position", "OPEN"),
    ("decision", "EXITED", "position", "OPEN"),
    ("decision", "EXITED", "position", "OPENING"),
)


def analyze_vocabulary(roots: LaneRoots | None = None) -> dict[str, Any]:
    roots = roots or resolve_lane_roots()
    with LaneImportContext(roots):
        from backend.nexus_decision.state_machine import (  # noqa: WPS433
            CANONICAL_STATES as DECISION_STATES,
            VALID_TRANSITIONS as DECISION_TRANSITIONS,
        )
        from backend.nexus_execution.contracts import (  # noqa: WPS433
            ORDER_STATES,
            POSITION_STATES,
        )

    shared_names = sorted(set(DECISION_STATES) & set(POSITION_STATES))
    # BLOCKED_AMBIGUOUS and CLOSED appear in both but with different transition graphs.
    mismatches: list[dict[str, Any]] = []
    if "CLOSED" in shared_names:
        mismatches.append(
            {
                "id": "VOCAB_SHARED_CLOSED",
                "severity": "high",
                "detail": (
                    "CLOSED exists in both Decision and Position vocabularies with different "
                    "semantics; no cross-lifecycle invariant enforces Decision CLOSED ⇒ Position "
                    "terminal."
                ),
            }
        )
    if "BLOCKED_AMBIGUOUS" in shared_names:
        mismatches.append(
            {
                "id": "VOCAB_SHARED_BLOCKED_AMBIGUOUS",
                "severity": "high",
                "detail": (
                    "BLOCKED_AMBIGUOUS is shared by Decision and Position state machines without "
                    "a joint recovery contract."
                ),
            }
        )

    # Decision allows MONITORING → UNDER_REVIEW → CLOSED without EXITED.
    monitoring_targets = set(DECISION_TRANSITIONS.get("MONITORING", frozenset()))
    if "UNDER_REVIEW" in monitoring_targets and "EXITED" in monitoring_targets:
        mismatches.append(
            {
                "id": "VOCAB_MONITORING_SKIP_EXIT",
                "severity": "critical",
                "detail": (
                    "Decision MONITORING may transition to UNDER_REVIEW (then CLOSED) without "
                    "EXITED, enabling Decision CLOSED while a synthetic position_id remains "
                    "conceptually open."
                ),
            }
        )

    return {
        "decision_states": list(DECISION_STATES),
        "position_states": sorted(POSITION_STATES),
        "order_states": sorted(ORDER_STATES),
        "shared_state_names": shared_names,
        "forbidden_combinations": [
            {
                "left_scope": a,
                "left_state": b,
                "right_scope": c,
                "right_state": d,
            }
            for a, b, c, d in FORBIDDEN_COMBINATIONS
        ],
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
    }
