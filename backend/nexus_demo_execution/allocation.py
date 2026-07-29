"""Margin allocation from available_balance with DEMO risk caps."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.nexus_demo_execution import FIXED_LEVERAGE, MAX_MARGIN, MAX_OPEN, MAX_PENDING, MIN_MARGIN
from backend.nexus_demo_execution.account_reader import DemoAccountSnapshot


class AllocationResult(str, Enum):
    ALLOCATED = "ALLOCATED"
    SKIP_INSUFFICIENT_SAFE_MARGIN = "SKIP_INSUFFICIENT_SAFE_MARGIN"
    INSUFFICIENT_DEMO_BALANCE = "INSUFFICIENT_DEMO_BALANCE"
    MAX_OPEN_REACHED = "MAX_OPEN_REACHED"
    MAX_PENDING_REACHED = "MAX_PENDING_REACHED"
    MAX_MARGIN_EXCEEDED = "MAX_MARGIN_EXCEEDED"


@dataclass
class AllocationDecision:
    result: AllocationResult
    margin_usdt: float = 0.0
    leverage: int = FIXED_LEVERAGE
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result.value,
            "margin_usdt": self.margin_usdt,
            "leverage": self.leverage,
            "reason": self.reason,
        }


@dataclass
class MarginAllocator:
    """Allocate margin from available_balance — never from invented balances."""

    min_margin: float = MIN_MARGIN
    max_margin: float = MAX_MARGIN
    max_open: int = MAX_OPEN
    max_pending: int = MAX_PENDING
    fixed_leverage: int = FIXED_LEVERAGE

    def allocate(
        self,
        snap: DemoAccountSnapshot,
        *,
        requested_margin: float,
        open_count: int | None = None,
        pending_count: int | None = None,
    ) -> AllocationDecision:
        open_count = open_count if open_count is not None else len(snap.open_positions)
        pending_count = pending_count if pending_count is not None else len(snap.open_orders)

        available = snap.available_balance
        if available < self.min_margin:
            return AllocationDecision(
                result=AllocationResult.SKIP_INSUFFICIENT_SAFE_MARGIN,
                reason=f"available={available:.2f} < min={self.min_margin}",
            )

        if open_count >= self.max_open:
            return AllocationDecision(
                result=AllocationResult.MAX_OPEN_REACHED,
                reason=f"open={open_count} >= max={self.max_open}",
            )

        if pending_count >= self.max_pending:
            return AllocationDecision(
                result=AllocationResult.MAX_PENDING_REACHED,
                reason=f"pending={pending_count} >= max={self.max_pending}",
            )

        cap = min(requested_margin, self.max_margin, available)
        if cap < self.min_margin:
            return AllocationDecision(
                result=AllocationResult.INSUFFICIENT_DEMO_BALANCE,
                reason=f"capped={cap:.2f} < min={self.min_margin}",
            )

        if requested_margin > available:
            return AllocationDecision(
                result=AllocationResult.INSUFFICIENT_DEMO_BALANCE,
                reason=f"requested={requested_margin:.2f} > available={available:.2f}",
            )

        return AllocationDecision(
            result=AllocationResult.ALLOCATED,
            margin_usdt=cap,
            leverage=self.fixed_leverage,
            reason="allocated_from_available_balance",
        )
