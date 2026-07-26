"""Demo order execution — order adapter (interface only).

Write methods ALWAYS raise WriteNotAuthorizedError.
Must NOT call exchange write even if credentials are present.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_execution.intent import (
    DemoOrderIntent,
    WriteNotAuthorizedError,
)

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False
WRITE_ALLOWED: bool = False


@dataclass
class AdapterReadResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class DemoOrderAdapter:
    """Interface-only adapter. Write methods unconditionally raise.

    Even if exchange credentials exist, this adapter NEVER calls
    exchange write endpoints (place, amend, cancel, set-leverage,
    transfer, withdraw).
    """

    def __init__(self) -> None:
        self._write_attempts: int = 0

    @property
    def write_allowed(self) -> bool:
        return False

    @property
    def write_attempts(self) -> int:
        return self._write_attempts

    def place_order(self, intent: DemoOrderIntent) -> None:
        """NEVER sends orders. Always raises."""
        self._write_attempts += 1
        raise WriteNotAuthorizedError(
            f"DemoOrderAdapter.place_order BLOCKED: "
            f"write not authorized for {intent.symbol} {intent.side}. "
            f"order_sent=False always."
        )

    def amend_order(self, order_id: str, **kwargs: Any) -> None:
        """NEVER amends orders. Always raises."""
        self._write_attempts += 1
        raise WriteNotAuthorizedError(
            f"DemoOrderAdapter.amend_order BLOCKED: "
            f"write not authorized for order {order_id}."
        )

    def cancel_order(self, order_id: str) -> None:
        """NEVER cancels orders via exchange. Always raises."""
        self._write_attempts += 1
        raise WriteNotAuthorizedError(
            f"DemoOrderAdapter.cancel_order BLOCKED: "
            f"write not authorized for order {order_id}."
        )

    def set_leverage(self, symbol: str, leverage: int) -> None:
        """NEVER sets leverage on exchange. Always raises."""
        self._write_attempts += 1
        raise WriteNotAuthorizedError(
            f"DemoOrderAdapter.set_leverage BLOCKED: "
            f"write not authorized for {symbol} leverage={leverage}."
        )

    def close_position(self, symbol: str, side: str, qty: float) -> None:
        """NEVER closes positions on exchange. Always raises."""
        self._write_attempts += 1
        raise WriteNotAuthorizedError(
            f"DemoOrderAdapter.close_position BLOCKED: "
            f"write not authorized for {symbol} {side} qty={qty}."
        )

    def transfer(self, **kwargs: Any) -> None:
        """NEVER transfers funds. Always raises."""
        self._write_attempts += 1
        raise WriteNotAuthorizedError("DemoOrderAdapter.transfer BLOCKED.")

    def withdraw(self, **kwargs: Any) -> None:
        """NEVER withdraws funds. Always raises."""
        self._write_attempts += 1
        raise WriteNotAuthorizedError("DemoOrderAdapter.withdraw BLOCKED.")

    def query_order_status(self, order_id: str) -> AdapterReadResult:
        """Read-only query — allowed but returns stub in this phase."""
        return AdapterReadResult(
            success=True,
            data={"orderId": order_id, "status": "QUERY_ONLY_STUB", "orderSent": False},
        )

    def summary(self) -> dict[str, Any]:
        return {
            "writeAllowed": False,
            "writeAttempts": self._write_attempts,
            "allWritesBlocked": True,
            "orderSent": False,
        }
