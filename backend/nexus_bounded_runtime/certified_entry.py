"""Certified persist-before-submit entry using DurableOrderLedger."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger, OrderIntent, make_order_link_id
from backend.nexus_demo_execution.order_reconciliation import BybitDemoReconciler
from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID

BOUNDED_RECONCILE_ATTEMPTS = 3


def candidate_to_market_input(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": candidate.get("symbol"),
        "side": candidate.get("direction") or candidate.get("side"),
        "confidence": candidate.get("confidence") or candidate.get("candidate_score"),
        "expected_gross_pnl": candidate.get("expected_gross_pnl") or "UNKNOWN",
        "round_trip_fee_estimate": candidate.get("round_trip_fee_estimate") or "UNKNOWN",
        "market_regime": candidate.get("regime") or "UNKNOWN",
        "signal_family": candidate.get("strategy") or "UNKNOWN",
    }


def persist_durable_intent(
    *,
    ledger: DurableOrderLedger,
    symbol: str,
    side: str,
    qty: str,
    campaign_id: str = P1_CAMPAIGN_ID,
) -> tuple[str, str, str]:
    order_intent_id = f"bd6h_{uuid.uuid4().hex[:16]}"
    decision_id = f"bdec_{uuid.uuid4().hex[:16]}"
    trade_id = f"btrd_{uuid.uuid4().hex[:16]}"
    intent = OrderIntent(
        order_intent_id=order_intent_id,
        decision_id=decision_id,
        trade_id=trade_id,
        campaign_id=campaign_id,
        symbol=symbol,
        side=side,
        requested_qty=Decimal(str(qty)),
        order_type="Market",
    )
    order_link_id = ledger.create_intent(intent)
    ledger.transition(order_intent_id, "SUBMITTING", source="bounded_pre_submit")
    bound = make_order_link_id(campaign_id, decision_id, order_intent_id)
    if order_link_id != bound:
        raise ValueError("orderlink_not_bound_to_durable_intent")
    return order_intent_id, order_link_id, trade_id


def reconcile_submit_unknown(
    *,
    ledger: DurableOrderLedger,
    reconciler: BybitDemoReconciler,
    writer: Any,
    order_intent_id: str,
    order_link_id: str,
    symbol: str,
) -> dict[str, Any]:
    record = ledger.get_intent(order_intent_id)
    if record is None:
        return {"ok": False, "reason": "intent_missing", "hold": True}
    last_state = str(record.get("state") or "")
    for _ in range(BOUNDED_RECONCILE_ATTEMPTS):
        found = None
        if getattr(writer, "find_order", None):
            found = writer.find_order(symbol=symbol, order_link_id=order_link_id)
        if found:
            ack_id = str(found.get("orderId") or found.get("order_id") or "")
            if ack_id and str(record.get("state")) in {"SUBMITTING", "SUBMIT_UNKNOWN"}:
                ledger.transition(
                    order_intent_id,
                    "ACCEPTED",
                    source="exact_orderlink_reconcile",
                    exchange={"order_id": ack_id, "status": found.get("orderStatus") or "Created"},
                )
            state = reconciler.reconcile_intent(ledger.get_intent(order_intent_id) or record)
            return {
                "ok": True,
                "recovered": True,
                "order_intent_id": order_intent_id,
                "order_link_id": order_link_id,
                "bybit_order_id": ack_id,
                "reconciled_state": state,
                "blind_retry": False,
            }
        if getattr(reconciler, "reconcile_intent", None):
            state = reconciler.reconcile_intent(record)
            last_state = state
            if state not in {"NOT_FOUND", "RECONCILIATION_REQUIRED", "SUBMIT_UNKNOWN"}:
                return {
                    "ok": True,
                    "recovered": True,
                    "order_intent_id": order_intent_id,
                    "reconciled_state": state,
                    "blind_retry": False,
                }
    updated = ledger.get_intent(order_intent_id) or record
    if last_state == "NOT_FOUND" and str(updated.get("state")) == "SUBMIT_UNKNOWN":
        ledger.transition(order_intent_id, "REJECTED", source="submit_unknown_proven_absent")
        return {"ok": False, "reason": "submit_unknown_proven_absent", "terminal": "REJECTED", "blind_retry": False}
    return {
        "ok": False,
        "reason": "submit_unknown_unresolved",
        "hold": True,
        "state": str(updated.get("state") or last_state),
        "blind_retry": False,
    }


def submit_after_persist(
    *,
    ledger: DurableOrderLedger,
    reconciler: BybitDemoReconciler,
    writer: Any,
    order_intent_id: str,
    order_link_id: str,
    symbol: str,
    side: str,
    qty: str,
    stop_loss: str | None = None,
    take_profit: str | None = None,
    submit_attempts: dict[str, int] | None = None,
) -> dict[str, Any]:
    attempts = submit_attempts if submit_attempts is not None else {}
    record = ledger.get_intent(order_intent_id)
    if record is None:
        return {"ok": False, "reason": "durable_intent_not_ready", "create_order_calls": 0}

    prior_attempts = int(attempts.get(order_link_id) or 0)
    if prior_attempts >= 1:
        recovered = reconcile_submit_unknown(
            ledger=ledger,
            reconciler=reconciler,
            writer=writer,
            order_intent_id=order_intent_id,
            order_link_id=order_link_id,
            symbol=symbol,
        )
        recovered["create_order_calls"] = 0
        recovered["blocked"] = "NO_BLIND_RETRY"
        return recovered

    if str(record.get("state")) != "SUBMITTING":
        return {"ok": False, "reason": "durable_intent_not_ready", "create_order_calls": 0}

    create_order_calls = 0
    try:
        if getattr(writer, "set_leverage", None):
            writer.set_leverage(symbol, 25)
        create_order_calls = 1
        attempts[order_link_id] = prior_attempts + 1
        resp = writer.create_market_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_link_id=order_link_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
    except Exception as exc:  # noqa: BLE001
        ledger.transition(
            order_intent_id,
            "SUBMIT_UNKNOWN",
            source="bybit_create_error",
            exchange={"reject_reason": type(exc).__name__},
        )
        unknown = reconcile_submit_unknown(
            ledger=ledger,
            reconciler=reconciler,
            writer=writer,
            order_intent_id=order_intent_id,
            order_link_id=order_link_id,
            symbol=symbol,
        )
        unknown["create_order_calls"] = create_order_calls
        unknown["exchange_write_attempt_total"] = create_order_calls
        unknown["submit_error"] = type(exc).__name__
        return unknown

    result = resp.get("result") if isinstance(resp, dict) else {}
    if not isinstance(result, dict):
        result = resp if isinstance(resp, dict) else {}
    ack_id = str(result.get("orderId") or result.get("order_id") or "")
    if ack_id:
        ledger.transition(
            order_intent_id,
            "ACCEPTED",
            source="bybit_create_ack",
            exchange={"order_id": ack_id, "status": "Created"},
        )
    else:
        ledger.transition(order_intent_id, "SUBMIT_UNKNOWN", source="bybit_create_ack_missing_id")
        unknown = reconcile_submit_unknown(
            ledger=ledger,
            reconciler=reconciler,
            writer=writer,
            order_intent_id=order_intent_id,
            order_link_id=order_link_id,
            symbol=symbol,
        )
        unknown["create_order_calls"] = create_order_calls
        unknown["exchange_write_attempt_total"] = create_order_calls
        return unknown
    state = reconciler.reconcile_intent(ledger.get_intent(order_intent_id) or record)
    return {
        "ok": True,
        "order_intent_id": order_intent_id,
        "order_link_id": order_link_id,
        "bybit_order_id": ack_id,
        "reconciled_state": state,
        "create_order_calls": create_order_calls,
        "exchange_write_attempt_total": create_order_calls,
        "blind_retry": False,
    }
