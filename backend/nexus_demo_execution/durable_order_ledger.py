"""PostgreSQL authoritative Bybit Demo order intent and reconciliation ledger.

This module deliberately persists intent before a client may submit it.  It
does not arm trading or create orders by itself.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.nexus_persistence_pg.pool import PostgresPool


FINAL_STATES = frozenset({"CLOSED", "CANCELLED", "REJECTED"})
ALLOWED_TRANSITIONS = {
    "INTENT_CREATED": {"SUBMITTING", "RECONCILIATION_REQUIRED"},
    "SUBMITTING": {"SUBMIT_UNKNOWN", "ACCEPTED", "REJECTED", "RECONCILIATION_REQUIRED"},
    "SUBMIT_UNKNOWN": {"ACCEPTED", "NEW", "PARTIALLY_FILLED", "FILLED", "REJECTED", "RECONCILIATION_REQUIRED"},
    "ACCEPTED": {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCEL_REQUESTED", "REJECTED", "RECONCILIATION_REQUIRED"},
    "NEW": {"PARTIALLY_FILLED", "FILLED", "CANCEL_REQUESTED", "CANCELLED", "REJECTED", "RECONCILIATION_REQUIRED"},
    "PARTIALLY_FILLED": {"FILLED", "CANCEL_REQUESTED", "CANCELLED", "CLOSE_PENDING", "RECONCILIATION_REQUIRED"},
    "FILLED": {"CLOSE_PENDING", "CLOSED", "RECONCILIATION_REQUIRED"},
    "CANCEL_REQUESTED": {"CANCELLED", "PARTIALLY_FILLED", "FILLED", "RECONCILIATION_REQUIRED"},
    "CLOSE_PENDING": {"CLOSED", "PARTIALLY_FILLED", "RECONCILIATION_REQUIRED"},
    "RECONCILIATION_REQUIRED": {"ACCEPTED", "NEW", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED", "CLOSED"},
}


def make_order_link_id(campaign_id: str, decision_id: str, order_intent_id: str) -> str:
    """Stable Bybit-safe ID, <=36 chars, derived from durable identities."""
    digest = hashlib.sha256(f"{campaign_id}|{decision_id}|{order_intent_id}".encode()).hexdigest()[:28]
    return f"nx-{digest}"  # 31 chars: no secrets, retry/restart stable.


@dataclass(frozen=True)
class OrderIntent:
    order_intent_id: str
    decision_id: str
    trade_id: str
    campaign_id: str
    symbol: str
    side: str
    requested_qty: Decimal
    order_type: str
    requested_price: Decimal | None = None
    position_idx: int = 0
    reduce_only: bool = False


class DurableOrderLedger:
    def __init__(self, pool: PostgresPool):
        self.pool = pool

    def create_intent(self, intent: OrderIntent) -> str:
        if not re.fullmatch(r"[A-Z0-9]{3,32}", intent.symbol):
            raise ValueError("invalid_symbol")
        if intent.side not in {"Buy", "Sell"} or intent.requested_qty <= 0:
            raise ValueError("invalid_order_intent")
        order_link_id = make_order_link_id(intent.campaign_id, intent.decision_id, intent.order_intent_id)
        with self.pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO nexus.bybit_demo_order_intents
                        (order_intent_id,decision_id,trade_id,campaign_id,order_link_id,symbol,side,
                         position_idx,order_type,requested_qty,requested_price,reduce_only,state,remaining_qty)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'INTENT_CREATED',%s)
                        """,
                        (intent.order_intent_id, intent.decision_id, intent.trade_id, intent.campaign_id,
                         order_link_id, intent.symbol, intent.side, intent.position_idx, intent.order_type,
                         intent.requested_qty, intent.requested_price, intent.reduce_only, intent.requested_qty),
                    )
                    self._history(cur, intent.order_intent_id, None, "INTENT_CREATED", "local_intent", {})
        return order_link_id

    def transition(self, order_intent_id: str, state: str, *, source: str, exchange: dict[str, Any] | None = None) -> None:
        if state not in {item for values in ALLOWED_TRANSITIONS.values() for item in values} | {"INTENT_CREATED"}:
            raise ValueError("invalid_order_state")
        exchange = exchange or {}
        with self.pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT state FROM nexus.bybit_demo_order_intents WHERE order_intent_id=%s FOR UPDATE",
                        (order_intent_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ValueError("order_intent_not_found")
                    previous = row[0]
                    if state != previous and state not in ALLOWED_TRANSITIONS.get(previous, set()):
                        raise ValueError(f"invalid_transition:{previous}->{state}")
                    cur.execute(
                        """
                        UPDATE nexus.bybit_demo_order_intents
                        SET state=%s, bybit_order_id=COALESCE(%s,bybit_order_id),
                            exchange_status=COALESCE(%s,exchange_status),
                            filled_qty=COALESCE(%s,filled_qty), remaining_qty=COALESCE(%s,remaining_qty),
                            avg_fill_price=COALESCE(%s,avg_fill_price), fees=COALESCE(%s,fees),
                            reject_reason=COALESCE(%s,reject_reason), last_reconciled_at=NOW(), updated_at=NOW()
                        WHERE order_intent_id=%s
                        """,
                        (state, exchange.get("order_id"), exchange.get("status"), exchange.get("filled_qty"),
                         exchange.get("remaining_qty"), exchange.get("avg_fill_price"), exchange.get("fees"),
                         exchange.get("reject_reason"), order_intent_id),
                    )
                    self._history(cur, order_intent_id, previous, state, source, exchange)

    def unfinished(self) -> list[dict[str, Any]]:
        rows = self.pool.fetchall(
            """SELECT order_intent_id,order_link_id,symbol,side,state,bybit_order_id,requested_qty,filled_qty
               FROM nexus.bybit_demo_order_intents
               WHERE state NOT IN ('CLOSED','CANCELLED','REJECTED') ORDER BY created_at""",
        )
        return [
            {"order_intent_id": r[0], "order_link_id": r[1], "symbol": r[2], "side": r[3],
             "state": r[4], "bybit_order_id": r[5], "requested_qty": str(r[6]), "filled_qty": str(r[7])}
            for r in rows
        ]

    @staticmethod
    def _history(cur: Any, intent_id: str, previous: str | None, state: str, source: str, detail: dict[str, Any]) -> None:
        cur.execute(
            """INSERT INTO nexus.bybit_demo_order_state_history
               (transition_id,order_intent_id,from_state,to_state,source,detail_json)
               VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
            (f"ordtr_{uuid.uuid4().hex[:20]}", intent_id, previous, state, source, json.dumps(detail)),
        )
