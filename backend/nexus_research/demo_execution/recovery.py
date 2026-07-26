"""Demo order execution — order recovery.

Handles AMBIGUOUS and RECOVERY_REQUIRED states.
Recovery always queries exchange state first, never blind-resends.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_execution.adapter import AdapterReadResult, DemoOrderAdapter
from backend.nexus_research.demo_execution.state_machine import (
    DemoOrderState,
    DemoOrderStateMachine,
)

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False


@dataclass
class RecoveryAction:
    action: str  # QUERY_EXCHANGE | MARK_REJECTED | MARK_CANCELLED | MANUAL_REVIEW | NO_ACTION
    order_id: str
    reason: str
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "orderId": self.order_id,
            "reason": self.reason,
            "timestampMs": self.timestamp_ms,
            "resolved": self.resolved,
            "orderSent": False,
        }


class DemoOrderRecovery:
    """Recovery handler — always queries first, never resends.

    Policy:
    - AMBIGUOUS: query exchange → resolve to ACKNOWLEDGED/REJECTED/CANCELLED
    - RECOVERY_REQUIRED: requires manual review, cannot auto-resolve to send
    - NEVER blind-resend an order
    """

    def __init__(self, adapter: DemoOrderAdapter | None = None) -> None:
        self._adapter = adapter or DemoOrderAdapter()
        self._actions: list[RecoveryAction] = []

    @property
    def actions(self) -> list[RecoveryAction]:
        return list(self._actions)

    def attempt_recovery(
        self,
        order_id: str,
        sm: DemoOrderStateMachine,
    ) -> RecoveryAction:
        """Attempt to recover an order in AMBIGUOUS or RECOVERY_REQUIRED state."""
        if sm.state == DemoOrderState.AMBIGUOUS:
            query_result = self._adapter.query_order_status(order_id)
            action = self._resolve_ambiguous(order_id, sm, query_result)
            self._actions.append(action)
            return action

        if sm.state == DemoOrderState.RECOVERY_REQUIRED:
            action = RecoveryAction(
                action="MANUAL_REVIEW",
                order_id=order_id,
                reason="RECOVERY_REQUIRED state needs manual review — never auto-resend",
                resolved=False,
            )
            self._actions.append(action)
            return action

        action = RecoveryAction(
            action="NO_ACTION",
            order_id=order_id,
            reason=f"Order in {sm.state.value} — no recovery needed",
            resolved=True,
        )
        self._actions.append(action)
        return action

    def _resolve_ambiguous(
        self,
        order_id: str,
        sm: DemoOrderStateMachine,
        query: AdapterReadResult,
    ) -> RecoveryAction:
        if not query.success:
            sm.transition(
                DemoOrderState.RECOVERY_REQUIRED,
                reason="exchange query failed during ambiguous recovery",
            )
            return RecoveryAction(
                action="MANUAL_REVIEW",
                order_id=order_id,
                reason="Exchange query failed — escalating to RECOVERY_REQUIRED",
                resolved=False,
            )

        exchange_status = query.data.get("status", "UNKNOWN")

        if exchange_status in {"REJECTED", "Rejected", "Deactivated"}:
            sm.transition(DemoOrderState.REJECTED, reason=f"exchange reports {exchange_status}")
            return RecoveryAction(
                action="MARK_REJECTED",
                order_id=order_id,
                reason=f"Exchange confirmed: {exchange_status}",
                resolved=True,
            )

        if exchange_status in {"CANCELLED", "Cancelled"}:
            sm.transition(DemoOrderState.CANCELLED, reason=f"exchange reports {exchange_status}")
            return RecoveryAction(
                action="MARK_CANCELLED",
                order_id=order_id,
                reason=f"Exchange confirmed: {exchange_status}",
                resolved=True,
            )

        return RecoveryAction(
            action="QUERY_EXCHANGE",
            order_id=order_id,
            reason=f"Exchange status={exchange_status} — query only, no resend",
            resolved=False,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "actionCount": len(self._actions),
            "resolvedCount": sum(1 for a in self._actions if a.resolved),
            "blindResendCount": 0,
            "orderSent": False,
        }
