"""Certified persist-before-submit entry using DurableOrderLedger."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger, OrderIntent, make_order_link_id
from backend.nexus_demo_execution.order_reconciliation import BybitDemoReconciler
from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID


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
) -> dict[str, Any]:
    record = ledger.get_intent(order_intent_id)
    if record is None or str(record.get("state")) != "SUBMITTING":
        return {"ok": False, "reason": "durable_intent_not_ready", "create_order_calls": 0}
    try:
        if getattr(writer, "set_leverage", None):
            writer.set_leverage(symbol, 25)
        create_order_calls = 1
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
        return {"ok": False, "reason": f"submit_unknown:{type(exc).__name__}", "create_order_calls": 0}
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
        return {"ok": False, "reason": "submit_unknown_missing_ack", "create_order_calls": create_order_calls}
    state = reconciler.reconcile_intent(ledger.get_intent(order_intent_id) or record)
    return {
        "ok": True,
        "order_intent_id": order_intent_id,
        "order_link_id": order_link_id,
        "bybit_order_id": ack_id,
        "reconciled_state": state,
        "create_order_calls": create_order_calls,
    }
