"""Cross-lifecycle invariants and snapshot validation."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.nexus_contracts.lifecycle.adapters import ControlPlaneSessionAdapter
from backend.nexus_contracts.lifecycle.ontology import (
    INTENT_UNRESOLVED,
    ORDER_TERMINALS,
    POSITION_OPEN_LIKE,
)

# Machine-readable invariant catalog. Codes are stable for CI/artifacts.
CROSS_LIFECYCLE_INVARIANTS: tuple[dict[str, str], ...] = (
    {
        "code": "INV_DECISION_CLOSED_POSITION_OPEN",
        "severity": "critical",
        "rule": "Decision CLOSED forbids Position OPEN/OPENING/REDUCING",
    },
    {
        "code": "INV_SESSION_COMPLETED_UNRESOLVED_INTENT",
        "severity": "critical",
        "rule": "Session COMPLETED forbids unresolved Intent",
    },
    {
        "code": "INV_REFLECTION_COMPLETE_BEFORE_EXIT",
        "severity": "critical",
        "rule": "Reflection COMPLETE requires exit evidence (Decision EXITED|CLOSED or exit_evidence=true)",
    },
    {
        "code": "INV_POSITION_CLOSED_RESIDUAL_QTY",
        "severity": "critical",
        "rule": "Position CLOSED forbids residual quantity > 0",
    },
    {
        "code": "INV_SESSION_COMPLETED_OPEN_POSITION",
        "severity": "critical",
        "rule": "Session COMPLETED forbids open-like Position",
    },
    {
        "code": "INV_DECISION_CLOSED_NONTERMINAL_ORDER",
        "severity": "critical",
        "rule": "Decision CLOSED forbids non-terminal Order",
    },
    {
        "code": "INV_SESSION_CONTROL_ADAPTER",
        "severity": "critical",
        "rule": "Session+ControlPlane joint snapshot must pass explicit adapter (no silent homonym)",
    },
    {
        "code": "INV_INTENT_RESOLVED_ORDER_CONSISTENCY",
        "severity": "high",
        "rule": "Intent FILLED implies Order FILLED (when order_state present)",
    },
)


def _dec(value: Any) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def validate_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Validate a multi-scope lifecycle snapshot.

    Expected keys (all optional except when checking a specific invariant):
      decision_state, session_state, intent_state, order_state, position_state,
      reflection_state, control_plane_state, position_qty, exit_evidence (bool)
    """
    violations: list[dict[str, Any]] = []

    decision = snapshot.get("decision_state")
    session = snapshot.get("session_state")
    intent = snapshot.get("intent_state")
    order = snapshot.get("order_state")
    position = snapshot.get("position_state")
    reflection = snapshot.get("reflection_state")
    control = snapshot.get("control_plane_state")
    qty = _dec(snapshot.get("position_qty"))
    exit_evidence = bool(snapshot.get("exit_evidence", False))

    # 1) Decision CLOSED + Position OPEN = invalid
    if decision == "CLOSED" and position in POSITION_OPEN_LIKE:
        violations.append(
            {
                "code": "INV_DECISION_CLOSED_POSITION_OPEN",
                "severity": "critical",
                "detail": f"decision=CLOSED position={position}",
            }
        )

    # 2) Session COMPLETED + unresolved Intent = invalid
    if session == "COMPLETED" and intent in INTENT_UNRESOLVED:
        violations.append(
            {
                "code": "INV_SESSION_COMPLETED_UNRESOLVED_INTENT",
                "severity": "critical",
                "detail": f"session=COMPLETED intent={intent}",
            }
        )

    # 3) Reflection COMPLETE before Exit evidence = invalid
    if reflection == "COMPLETE":
        decision_exit_ok = decision in {"EXITED", "CLOSED", "UNDER_REVIEW", "CALIBRATED"}
        if not (exit_evidence or decision_exit_ok):
            violations.append(
                {
                    "code": "INV_REFLECTION_COMPLETE_BEFORE_EXIT",
                    "severity": "critical",
                    "detail": (
                        f"reflection=COMPLETE exit_evidence={exit_evidence} "
                        f"decision={decision}"
                    ),
                }
            )

    # 4) Position CLOSED + residual quantity > 0 = invalid
    if position == "CLOSED" and qty > 0:
        violations.append(
            {
                "code": "INV_POSITION_CLOSED_RESIDUAL_QTY",
                "severity": "critical",
                "detail": f"position=CLOSED qty={qty}",
            }
        )

    # 5) Session COMPLETED + open position
    if session == "COMPLETED" and position in POSITION_OPEN_LIKE:
        violations.append(
            {
                "code": "INV_SESSION_COMPLETED_OPEN_POSITION",
                "severity": "critical",
                "detail": f"session=COMPLETED position={position}",
            }
        )

    # 6) Decision CLOSED + non-terminal order
    if decision == "CLOSED" and order is not None and order not in ORDER_TERMINALS:
        violations.append(
            {
                "code": "INV_DECISION_CLOSED_NONTERMINAL_ORDER",
                "severity": "critical",
                "detail": f"decision=CLOSED order={order}",
            }
        )

    # 7) Session + ControlPlane adapter
    if session is not None and control is not None:
        adapter = ControlPlaneSessionAdapter()
        if not adapter.is_compatible(session, control):
            violations.append(
                {
                    "code": "INV_SESSION_CONTROL_ADAPTER",
                    "severity": "critical",
                    "detail": f"unmapped pair session={session} control={control}",
                }
            )

    # 8) Intent FILLED ⇒ Order FILLED
    if intent == "FILLED" and order is not None and order != "FILLED":
        violations.append(
            {
                "code": "INV_INTENT_RESOLVED_ORDER_CONSISTENCY",
                "severity": "high",
                "detail": f"intent=FILLED order={order}",
            }
        )

    critical = [v for v in violations if v.get("severity") == "critical"]
    return {
        "schema": "nexus_lifecycle_snapshot_validation_v11_1",
        "valid": len(critical) == 0,
        "violation_count": len(violations),
        "critical_count": len(critical),
        "violations": violations,
        "snapshot": dict(snapshot),
    }
