"""Demo order execution — close controller.

Manages the close lifecycle for demo positions.
Close requires separate authorization. Adapter blocks actual close.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_execution.adapter import DemoOrderAdapter
from backend.nexus_research.demo_execution.intent import (
    DemoOrderAuthorization,
    DemoOrderIntent,
    NotAuthorizedError,
    WriteNotAuthorizedError,
)
from backend.nexus_research.demo_execution.state_machine import (
    DemoOrderState,
    DemoOrderStateMachine,
)

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False


@dataclass
class CloseRequest:
    order_id: str
    symbol: str
    side: str
    qty: float
    reason: str  # STOP_LOSS | TAKE_PROFIT | MANUAL | TIMEOUT
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    order_sent: bool = field(default=False, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "orderId": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "reason": self.reason,
            "createdAtMs": self.created_at_ms,
            "orderSent": False,
        }


@dataclass
class CloseResult:
    success: bool
    order_id: str
    state: str
    reason: str
    order_sent: bool = field(default=False, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "orderId": self.order_id,
            "state": self.state,
            "reason": self.reason,
            "orderSent": False,
        }


class DemoCloseController:
    """Controls demo position close lifecycle.

    Transitions: FILLED/PARTIALLY_FILLED → CLOSE_AUTHORIZED → CLOSE_STARTED → CLOSED
    The adapter blocks actual close execution.
    """

    def __init__(self, adapter: DemoOrderAdapter | None = None) -> None:
        self._adapter = adapter or DemoOrderAdapter()
        self._close_log: list[CloseResult] = []

    def authorize_close(
        self,
        sm: DemoOrderStateMachine,
        request: CloseRequest,
    ) -> CloseResult:
        """Authorize a close. Does NOT execute — adapter blocks that."""
        if sm.state not in {DemoOrderState.FILLED, DemoOrderState.PARTIALLY_FILLED}:
            return CloseResult(
                success=False,
                order_id=request.order_id,
                state=sm.state.value,
                reason=f"Cannot close from state {sm.state.value}",
            )

        sm.transition(
            DemoOrderState.CLOSE_AUTHORIZED,
            reason=f"close authorized: {request.reason}",
        )

        result = CloseResult(
            success=True,
            order_id=request.order_id,
            state=sm.state.value,
            reason=f"Close authorized ({request.reason}). Adapter will block actual close.",
        )
        self._close_log.append(result)
        return result

    def attempt_close(
        self,
        sm: DemoOrderStateMachine,
        request: CloseRequest,
    ) -> CloseResult:
        """Attempt to close — adapter raises WriteNotAuthorizedError."""
        if sm.state != DemoOrderState.CLOSE_AUTHORIZED:
            return CloseResult(
                success=False,
                order_id=request.order_id,
                state=sm.state.value,
                reason=f"Must be CLOSE_AUTHORIZED, currently {sm.state.value}",
            )

        sm.transition(DemoOrderState.CLOSE_STARTED, reason="close attempt started")

        try:
            self._adapter.close_position(request.symbol, request.side, request.qty)
        except WriteNotAuthorizedError:
            sm.transition(
                DemoOrderState.AMBIGUOUS,
                reason="adapter blocked close — write not authorized",
            )
            result = CloseResult(
                success=False,
                order_id=request.order_id,
                state=sm.state.value,
                reason="Adapter correctly blocked close execution",
            )
            self._close_log.append(result)
            return result

        result = CloseResult(
            success=False,
            order_id=request.order_id,
            state=sm.state.value,
            reason="UNEXPECTED: adapter did not block (should never happen)",
        )
        self._close_log.append(result)
        return result

    @property
    def close_log(self) -> list[CloseResult]:
        return list(self._close_log)

    def summary(self) -> dict[str, Any]:
        return {
            "closeAttempts": len(self._close_log),
            "successfulCloses": sum(1 for r in self._close_log if r.success),
            "orderSent": False,
        }
