"""Fail-closed Bybit Demo reconciliation for durable order intents."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger


class BybitOrderReader(Protocol):
    def find_order(self, *, symbol: str, order_id: str = "", order_link_id: str = "") -> dict[str, Any] | None: ...
    def list_executions(self, *, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]: ...
    def list_positions(self, symbol: str | None = None) -> list[dict[str, Any]]: ...


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def exchange_state(order: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    status = str(order.get("orderStatus") or order.get("status") or "")
    filled = _decimal(order.get("cumExecQty") or order.get("cumExecValue") and 0)
    qty = _decimal(order.get("qty"))
    remaining = max(Decimal("0"), qty - filled)
    states = {
        "New": "NEW", "PartiallyFilled": "PARTIALLY_FILLED", "Filled": "FILLED",
        "Cancelled": "CANCELLED", "Rejected": "REJECTED",
    }
    return states.get(status, "RECONCILIATION_REQUIRED"), {
        "order_id": order.get("orderId"), "status": status, "filled_qty": filled,
        "remaining_qty": remaining, "avg_fill_price": _decimal(order.get("avgPrice")),
        "reject_reason": order.get("rejectReason") or None,
    }


class BybitDemoReconciler:
    def __init__(self, ledger: DurableOrderLedger, reader: BybitOrderReader):
        self.ledger = ledger
        self.reader = reader

    def reconcile_intent(self, record: dict[str, Any]) -> str:
        order = self.reader.find_order(
            symbol=record["symbol"], order_id=record.get("bybit_order_id") or "",
            order_link_id=record["order_link_id"],
        )
        if not order:
            self.ledger.transition(record["order_intent_id"], "RECONCILIATION_REQUIRED", source="bybit_not_found")
            return "NOT_FOUND"
        state, exchange = exchange_state(order)
        self.ledger.transition(record["order_intent_id"], state, source="bybit_order_lookup", exchange=exchange)
        return state

    def startup_reconcile(self) -> dict[str, Any]:
        unresolved: list[str] = []
        for record in self.ledger.unfinished():
            state = self.reconcile_intent(record)
            if state in {"NOT_FOUND", "RECONCILIATION_REQUIRED"}:
                unresolved.append(record["order_intent_id"])
        # Any non-empty exchange position with no matching local unfinished owner blocks entries.
        local_symbols = {item["symbol"] for item in self.ledger.unfinished()}
        orphan_positions = [p for p in self.reader.list_positions() if str(p.get("symbol") or "") not in local_symbols]
        return {
            "entries_allowed": not unresolved and not orphan_positions,
            "unresolved_intents": len(unresolved),
            "orphan_positions": len(orphan_positions),
        }
