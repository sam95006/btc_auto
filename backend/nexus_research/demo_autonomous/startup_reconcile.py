"""Startup reconciliation gate for autonomous Demo — query before new orders."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExchangeExposureSnapshot:
    positions: list[dict[str, Any]] = field(default_factory=list)
    open_orders: list[dict[str, Any]] = field(default_factory=list)
    recent_executions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def position_count(self) -> int:
        return sum(1 for p in self.positions if abs(float(p.get("size") or p.get("qty") or 0)) > 0)

    @property
    def open_order_count(self) -> int:
        return len(self.open_orders)


@dataclass
class StartupReconcileResult:
    allow_new_orders: bool
    status: str  # CLEAN | RECOVERY_REQUIRED | AMBIGUOUS
    reasons: list[str] = field(default_factory=list)
    position_count: int = 0
    open_order_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowNewOrders": self.allow_new_orders,
            "status": self.status,
            "reasons": list(self.reasons),
            "positionCount": self.position_count,
            "openOrderCount": self.open_order_count,
            "secretSafe": True,
        }


class AutonomousStartupReconciler:
    """Compare local vs exchange exposure; fail-closed on mismatch."""

    def reconcile(
        self,
        exchange: ExchangeExposureSnapshot,
        *,
        local_has_position: bool = False,
        local_has_order: bool = False,
        last_send_unacked: bool = False,
        ambiguous: bool = False,
    ) -> StartupReconcileResult:
        reasons: list[str] = []
        pos = exchange.position_count
        ords = exchange.open_order_count

        if ambiguous or last_send_unacked:
            reasons.append("ambiguous_or_unacked_send")
        if pos > 0 and not local_has_position:
            reasons.append("exchange_position_without_local")
        if pos == 0 and local_has_position:
            reasons.append("local_position_without_exchange")
        if ords > 0 and not local_has_order:
            reasons.append("exchange_order_without_local")
        if ords == 0 and local_has_order:
            reasons.append("local_order_without_exchange")
        if pos > 1:
            reasons.append("multiple_positions")
        if ords > 1:
            reasons.append("multiple_open_orders")

        if reasons:
            return StartupReconcileResult(
                allow_new_orders=False,
                status="RECOVERY_REQUIRED",
                reasons=reasons,
                position_count=pos,
                open_order_count=ords,
            )

        if pos > 0 or ords > 0:
            # Consistent exposure — no new orders until flat
            return StartupReconcileResult(
                allow_new_orders=False,
                status="CLEAN",
                reasons=["existing_exposure_hold"],
                position_count=pos,
                open_order_count=ords,
            )

        return StartupReconcileResult(
            allow_new_orders=True,
            status="CLEAN",
            reasons=[],
            position_count=0,
            open_order_count=0,
        )
