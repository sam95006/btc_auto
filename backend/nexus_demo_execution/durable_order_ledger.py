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

REQUIRED_P1_MIGRATIONS = ("0005", "0006")


def make_order_link_id(campaign_id: str, decision_id: str, order_intent_id: str) -> str:
    """Stable Bybit-safe ID, <=36 chars, derived from durable identities."""
    digest = hashlib.sha256(f"{campaign_id}|{decision_id}|{order_intent_id}".encode()).hexdigest()[:28]
    return f"nx-{digest}"  # 31 chars: no secrets, retry/restart stable.


def _json_detail(detail: dict[str, Any]) -> str:
    return json.dumps(detail or {}, default=str)


def _dec_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


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
    parent_order_intent_id: str | None = None


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
                         position_idx,order_type,requested_qty,requested_price,reduce_only,state,remaining_qty,
                         parent_order_intent_id)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'INTENT_CREATED',%s,%s)
                        """,
                        (intent.order_intent_id, intent.decision_id, intent.trade_id, intent.campaign_id,
                         order_link_id, intent.symbol, intent.side, intent.position_idx, intent.order_type,
                         intent.requested_qty, intent.requested_price, intent.reduce_only, intent.requested_qty,
                         intent.parent_order_intent_id),
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

    def get_intent(self, order_intent_id: str) -> dict[str, Any] | None:
        rows = self.pool.fetchall(
            """
            SELECT order_intent_id, decision_id, trade_id, campaign_id, order_link_id, symbol, side,
                   position_idx, order_type, requested_qty, requested_price, reduce_only, state,
                   bybit_order_id, exchange_status, filled_qty, remaining_qty, avg_fill_price, fees,
                   reject_reason, parent_order_intent_id, actual_entry_price, actual_exit_price,
                   realized_demo_pnl, wallet_delta, closed_at, pnl_provenance, accounting_json
            FROM nexus.bybit_demo_order_intents
            WHERE order_intent_id=%s
            """,
            (order_intent_id,),
        )
        if not rows:
            return None
        r = rows[0]
        accounting = r[27] if r[27] is not None else {}
        if isinstance(accounting, str):
            accounting = json.loads(accounting)
        return {
            "order_intent_id": r[0],
            "decision_id": r[1],
            "trade_id": r[2],
            "campaign_id": r[3],
            "order_link_id": r[4],
            "symbol": r[5],
            "side": r[6],
            "position_idx": r[7],
            "order_type": r[8],
            "requested_qty": _dec_str(r[9]),
            "requested_price": _dec_str(r[10]),
            "reduce_only": bool(r[11]),
            "state": r[12],
            "bybit_order_id": r[13],
            "exchange_status": r[14],
            "filled_qty": _dec_str(r[15]),
            "remaining_qty": _dec_str(r[16]),
            "avg_fill_price": _dec_str(r[17]),
            "fees": _dec_str(r[18]),
            "reject_reason": r[19],
            "parent_order_intent_id": r[20],
            "actual_entry_price": _dec_str(r[21]),
            "actual_exit_price": _dec_str(r[22]),
            "realized_demo_pnl": _dec_str(r[23]),
            "wallet_delta": _dec_str(r[24]),
            "closed_at": r[25].isoformat() if getattr(r[25], "isoformat", None) else r[25],
            "pnl_provenance": r[26],
            "accounting_json": accounting,
        }

    def list_campaign_intents(self, campaign_id: str) -> list[dict[str, Any]]:
        rows = self.pool.fetchall(
            """
            SELECT order_intent_id, decision_id, trade_id, campaign_id, order_link_id, symbol, side,
                   requested_qty, reduce_only, state, bybit_order_id, filled_qty, avg_fill_price,
                   parent_order_intent_id, actual_entry_price, actual_exit_price, realized_demo_pnl,
                   fees, closed_at, pnl_provenance, accounting_json, created_at
            FROM nexus.bybit_demo_order_intents
            WHERE campaign_id=%s
            ORDER BY created_at DESC, order_intent_id DESC
            """,
            (campaign_id,),
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            accounting = r[20] if r[20] is not None else {}
            if isinstance(accounting, str):
                accounting = json.loads(accounting)
            out.append(
                {
                    "order_intent_id": r[0],
                    "decision_id": r[1],
                    "trade_id": r[2],
                    "campaign_id": r[3],
                    "order_link_id": r[4],
                    "symbol": r[5],
                    "side": r[6],
                    "requested_qty": _dec_str(r[7]),
                    "reduce_only": bool(r[8]),
                    "state": r[9],
                    "bybit_order_id": r[10],
                    "filled_qty": _dec_str(r[11]),
                    "avg_fill_price": _dec_str(r[12]),
                    "parent_order_intent_id": r[13],
                    "actual_entry_price": _dec_str(r[14]),
                    "actual_exit_price": _dec_str(r[15]),
                    "realized_demo_pnl": _dec_str(r[16]),
                    "fees": _dec_str(r[17]),
                    "closed_at": r[18].isoformat() if getattr(r[18], "isoformat", None) else r[18],
                    "pnl_provenance": r[19],
                    "accounting_json": accounting,
                    "created_at": r[21].isoformat() if getattr(r[21], "isoformat", None) else r[21],
                }
            )
        return out

    def history(self, order_intent_id: str) -> list[dict[str, Any]]:
        rows = self.pool.fetchall(
            """
            SELECT transition_id, from_state, to_state, source, detail_json, occurred_at
            FROM nexus.bybit_demo_order_state_history
            WHERE order_intent_id=%s
            ORDER BY occurred_at, transition_id
            """,
            (order_intent_id,),
        )
        out: list[dict[str, Any]] = []
        for row in rows:
            detail = row[4] if row[4] is not None else {}
            if isinstance(detail, str):
                detail = json.loads(detail)
            out.append(
                {
                    "transition_id": row[0],
                    "from_state": row[1],
                    "to_state": row[2],
                    "source": row[3],
                    "detail": detail,
                    "occurred_at": row[5].isoformat() if getattr(row[5], "isoformat", None) else row[5],
                }
            )
        return out

    def record_accounting(
        self,
        order_intent_id: str,
        *,
        actual_entry_price: Any = None,
        actual_exit_price: Any = None,
        fees: Any = None,
        realized_demo_pnl: Any = None,
        wallet_delta: Any = None,
        closed_at: Any = None,
        pnl_provenance: str | None = None,
        accounting: dict[str, Any] | None = None,
    ) -> None:
        """Persist exchange-sourced accounting without inventing a state transition."""
        with self.pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT state FROM nexus.bybit_demo_order_intents WHERE order_intent_id=%s FOR UPDATE",
                        (order_intent_id,),
                    )
                    if not cur.fetchone():
                        raise ValueError("order_intent_not_found")
                    cur.execute(
                        """
                        UPDATE nexus.bybit_demo_order_intents
                        SET actual_entry_price=COALESCE(%s, actual_entry_price),
                            actual_exit_price=COALESCE(%s, actual_exit_price),
                            fees=COALESCE(%s, fees),
                            realized_demo_pnl=COALESCE(%s, realized_demo_pnl),
                            wallet_delta=COALESCE(%s, wallet_delta),
                            closed_at=COALESCE(%s, closed_at),
                            pnl_provenance=COALESCE(%s, pnl_provenance),
                            accounting_json=COALESCE(%s::jsonb, accounting_json),
                            updated_at=NOW()
                        WHERE order_intent_id=%s
                        """,
                        (
                            actual_entry_price,
                            actual_exit_price,
                            fees,
                            realized_demo_pnl,
                            wallet_delta,
                            closed_at,
                            pnl_provenance,
                            _json_detail(accounting) if accounting is not None else None,
                            order_intent_id,
                        ),
                    )

    def migration_versions(self) -> set[str]:
        rows = self.pool.fetchall("SELECT version FROM nexus.schema_migrations")
        return {str(row[0]) for row in rows}

    def required_migrations_present(self) -> dict[str, Any]:
        versions = self.migration_versions()
        missing = [item for item in REQUIRED_P1_MIGRATIONS if item not in versions]
        return {
            "ok": not missing,
            "present": sorted(versions),
            "missing": missing,
            "migration_0005_present": "0005" in versions,
            "migration_0006_present": "0006" in versions,
        }

    def probe_write_read(self) -> dict[str, Any]:
        """Transactional write/read that rolls back so unfinished intents stay clean."""

        class _Rollback(Exception):
            pass

        probe_id = f"p1probe_{uuid.uuid4().hex[:16]}"
        try:
            with self.pool.connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO nexus.bybit_demo_order_intents
                            (order_intent_id,decision_id,trade_id,campaign_id,order_link_id,symbol,side,
                             position_idx,order_type,requested_qty,reduce_only,state,remaining_qty)
                            VALUES (%s,'probe','probe','probe',%s,'BTCUSDT','Buy',0,'Market',0.001,false,
                                    'INTENT_CREATED',0.001)
                            """,
                            (probe_id, f"nx-probe-{probe_id[-12:]}"),
                        )
                        cur.execute(
                            "SELECT state FROM nexus.bybit_demo_order_intents WHERE order_intent_id=%s",
                            (probe_id,),
                        )
                        row = cur.fetchone()
                        if not row or row[0] != "INTENT_CREATED":
                            raise RuntimeError("ledger_probe_read_mismatch")
                        raise _Rollback()
        except _Rollback:
            leftover = self.pool.fetchval(
                "SELECT COUNT(*) FROM nexus.bybit_demo_order_intents WHERE order_intent_id=%s",
                (probe_id,),
            )
            return {"ok": leftover in (0, None), "probe_id_prefix": probe_id[:12], "rolled_back": leftover in (0, None)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": type(exc).__name__}

    @staticmethod
    def _history(cur: Any, intent_id: str, previous: str | None, state: str, source: str, detail: dict[str, Any]) -> None:
        cur.execute(
            """INSERT INTO nexus.bybit_demo_order_state_history
               (transition_id,order_intent_id,from_state,to_state,source,detail_json)
               VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
            (f"ordtr_{uuid.uuid4().hex[:20]}", intent_id, previous, state, source, _json_detail(detail)),
        )
