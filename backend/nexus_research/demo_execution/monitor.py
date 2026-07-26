"""Demo order execution — order monitor.

Watches order state, detects timeouts, marks AMBIGUOUS when
the exchange hasn't confirmed within the timeout window.

Never blind-resends. Always queries first.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_execution.state_machine import (
    DemoOrderState,
    DemoOrderStateMachine,
)

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False

DEFAULT_TIMEOUT_MS = 30_000
QUERY_BEFORE_RESEND: bool = True
BLIND_RESEND_ALLOWED: bool = False


@dataclass
class MonitorEvent:
    event_type: str  # TIMEOUT | STATE_CHECK | AMBIGUOUS_DETECTED
    order_id: str
    state: str
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventType": self.event_type,
            "orderId": self.order_id,
            "state": self.state,
            "timestampMs": self.timestamp_ms,
            "detail": self.detail,
        }


@dataclass
class TimeoutPolicy:
    """Never blind-resend. Query first. Ambiguous blocks new orders."""

    timeout_ms: int = DEFAULT_TIMEOUT_MS
    query_before_resend: bool = True
    blind_resend_allowed: bool = False
    ambiguous_blocks_new_orders: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeoutMs": self.timeout_ms,
            "queryBeforeResend": self.query_before_resend,
            "blindResendAllowed": False,
            "ambiguousBlocksNewOrders": self.ambiguous_blocks_new_orders,
        }


class DemoOrderMonitor:
    """Monitor order state and enforce timeout policy."""

    def __init__(self, *, timeout_policy: TimeoutPolicy | None = None) -> None:
        self._policy = timeout_policy or TimeoutPolicy()
        self._events: list[MonitorEvent] = []
        self._pending_since: dict[str, int] = {}

    @property
    def events(self) -> list[MonitorEvent]:
        return list(self._events)

    def start_monitoring(self, order_id: str) -> None:
        self._pending_since[order_id] = int(time.time() * 1000)

    def check_timeout(
        self,
        order_id: str,
        sm: DemoOrderStateMachine,
    ) -> MonitorEvent | None:
        """Check if an order has timed out in a non-terminal state.

        If timed out, transitions to AMBIGUOUS (never blind-resends).
        Returns the event if a timeout was detected, None otherwise.
        """
        started = self._pending_since.get(order_id)
        if started is None:
            return None

        now = int(time.time() * 1000)
        elapsed = now - started

        if elapsed < self._policy.timeout_ms:
            return None

        if sm.is_terminal or sm.state == DemoOrderState.AMBIGUOUS:
            return None

        if sm.state in {
            DemoOrderState.SEND_STARTED,
            DemoOrderState.CANCEL_PENDING,
            DemoOrderState.CLOSE_STARTED,
        }:
            sm.transition(
                DemoOrderState.AMBIGUOUS,
                reason=f"timeout after {elapsed}ms in {sm.state.value}",
            )
            event = MonitorEvent(
                event_type="TIMEOUT",
                order_id=order_id,
                state=sm.state.value,
                detail=(
                    f"Timed out after {elapsed}ms. "
                    f"Policy: query_before_resend={self._policy.query_before_resend}, "
                    f"blind_resend=NEVER"
                ),
            )
            self._events.append(event)
            return event

        return None

    def record_state_check(self, order_id: str, state: str) -> None:
        self._events.append(MonitorEvent(
            event_type="STATE_CHECK",
            order_id=order_id,
            state=state,
        ))

    def has_ambiguous_orders(self) -> bool:
        return any(e.event_type == "TIMEOUT" for e in self._events)

    def summary(self) -> dict[str, Any]:
        return {
            "eventCount": len(self._events),
            "pendingCount": len(self._pending_since),
            "hasAmbiguous": self.has_ambiguous_orders(),
            "policy": self._policy.to_dict(),
            "orderSent": False,
        }
