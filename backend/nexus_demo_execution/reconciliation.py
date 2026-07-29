"""Order/position reconciliation — MATCH / MISMATCH / AMBIGUOUS."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ReconciliationState(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class ReconciliationReport:
    state: ReconciliationState
    local_positions: int
    remote_positions: int
    local_orders: int
    remote_orders: int
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "local_positions": self.local_positions,
            "remote_positions": self.remote_positions,
            "local_orders": self.local_orders,
            "remote_orders": self.remote_orders,
            "detail": self.detail,
        }


@dataclass
class DemoReconciler:
    """Compare local ledger counts against remote account snapshot."""

    def reconcile(
        self,
        *,
        local_positions: list[dict[str, Any]],
        local_orders: list[dict[str, Any]],
        remote_positions: list[dict[str, Any]],
        remote_orders: list[dict[str, Any]],
        ambiguous: bool = False,
    ) -> ReconciliationReport:
        lp = len(local_positions)
        lo = len(local_orders)
        rp = len(remote_positions)
        ro = len(remote_orders)

        if ambiguous:
            return ReconciliationReport(
                state=ReconciliationState.AMBIGUOUS,
                local_positions=lp,
                remote_positions=rp,
                local_orders=lo,
                remote_orders=ro,
                detail="ambiguous_timeout_or_partial_data",
            )

        if lp == rp and lo == ro:
            return ReconciliationReport(
                state=ReconciliationState.MATCH,
                local_positions=lp,
                remote_positions=rp,
                local_orders=lo,
                remote_orders=ro,
                detail="counts_match",
            )

        return ReconciliationReport(
            state=ReconciliationState.MISMATCH,
            local_positions=lp,
            remote_positions=rp,
            local_orders=lo,
            remote_orders=ro,
            detail="count_mismatch",
        )
