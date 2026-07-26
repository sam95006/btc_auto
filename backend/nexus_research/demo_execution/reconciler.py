"""Demo order execution — order reconciler.

Compares internal ledger state with exchange query results.
Fail-closed: any mismatch blocks further operations.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_research.demo_execution.state_machine import (
    DemoOrderState,
    DemoOrderStateMachine,
)

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False


class OrderMismatchReason(str, Enum):
    NONE = "NONE"
    STATE_DIVERGENCE = "STATE_DIVERGENCE"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    SIDE_MISMATCH = "SIDE_MISMATCH"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    EXCHANGE_NOT_FOUND = "EXCHANGE_NOT_FOUND"
    LEDGER_NOT_FOUND = "LEDGER_NOT_FOUND"
    AMBIGUOUS_UNRESOLVED = "AMBIGUOUS_UNRESOLVED"


@dataclass
class OrderReconciliationResult:
    ok: bool
    status: str  # MATCH | MISMATCH | SKIPPED | FAIL_CLOSED
    order_id: str
    reasons: list[OrderMismatchReason] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    checked_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    order_sent: bool = field(default=False, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "orderId": self.order_id,
            "reasons": [r.value for r in self.reasons],
            "details": list(self.details),
            "checkedAtMs": self.checked_at_ms,
            "orderSent": False,
        }


class DemoOrderReconciler:
    """Compare internal order state with exchange query.

    Fail-closed: mismatch blocks new orders and requires manual review.
    """

    def reconcile(
        self,
        order_id: str,
        sm: DemoOrderStateMachine,
        *,
        exchange_state: str | None = None,
        exchange_qty: float | None = None,
        exchange_symbol: str | None = None,
        internal_qty: float | None = None,
        internal_symbol: str | None = None,
    ) -> OrderReconciliationResult:
        reasons: list[OrderMismatchReason] = []
        details: list[str] = []

        if sm.state == DemoOrderState.AMBIGUOUS:
            reasons.append(OrderMismatchReason.AMBIGUOUS_UNRESOLVED)
            details.append("order in AMBIGUOUS state — must resolve before reconcile")

        if exchange_state is not None and sm.state.value != exchange_state:
            reasons.append(OrderMismatchReason.STATE_DIVERGENCE)
            details.append(f"internal={sm.state.value} vs exchange={exchange_state}")

        if exchange_qty is not None and internal_qty is not None:
            if abs(exchange_qty - internal_qty) > 1e-8:
                reasons.append(OrderMismatchReason.QUANTITY_MISMATCH)
                details.append(f"internal_qty={internal_qty} vs exchange_qty={exchange_qty}")

        if exchange_symbol is not None and internal_symbol is not None:
            if exchange_symbol != internal_symbol:
                reasons.append(OrderMismatchReason.SYMBOL_MISMATCH)
                details.append(f"internal={internal_symbol} vs exchange={exchange_symbol}")

        ok = len(reasons) == 0
        return OrderReconciliationResult(
            ok=ok,
            status="MATCH" if ok else "MISMATCH",
            order_id=order_id,
            reasons=reasons,
            details=details,
        )

    def reconcile_to_state(
        self,
        sm: DemoOrderStateMachine,
        reconciliation: OrderReconciliationResult,
    ) -> None:
        """Transition SM to RECONCILED if match, or leave if mismatch."""
        if reconciliation.ok and sm.state in {
            DemoOrderState.FILLED,
            DemoOrderState.REJECTED,
            DemoOrderState.CANCELLED,
            DemoOrderState.CLOSED,
            DemoOrderState.AMBIGUOUS,
        }:
            sm.transition(DemoOrderState.RECONCILED, reason="reconciliation_match")
