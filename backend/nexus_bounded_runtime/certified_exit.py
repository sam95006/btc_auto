"""Certified persist-before-submit close using DurableOrderLedger — mirrors P1 close semantics."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from backend.nexus_bounded_runtime.certified_entry import BOUNDED_RECONCILE_ATTEMPTS, reconcile_submit_unknown
from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger, OrderIntent, make_order_link_id
from backend.nexus_demo_execution.order_reconciliation import BybitDemoReconciler
from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID


def persist_durable_close_intent(
    *,
    ledger: DurableOrderLedger,
    entry_intent_id: str,
    symbol: str,
    position_side: str,
    qty: str,
    campaign_id: str = P1_CAMPAIGN_ID,
) -> tuple[str, str]:
    entry = ledger.get_intent(entry_intent_id)
    if entry is None:
        raise ValueError("entry_intent_missing")
    close_intent_id = f"bd6hcls_{uuid.uuid4().hex[:12]}"
    close_side = "Sell" if str(position_side).lower() == "buy" else "Buy"
    intent = OrderIntent(
        order_intent_id=close_intent_id,
        decision_id=str(entry.get("decision_id") or ""),
        trade_id=str(entry.get("trade_id") or ""),
        campaign_id=campaign_id,
        symbol=symbol,
        side=close_side,
        requested_qty=Decimal(str(qty)),
        order_type="Market",
        reduce_only=True,
        parent_order_intent_id=entry_intent_id,
    )
    order_link_id = ledger.create_intent(intent)
    ledger.transition(entry_intent_id, "CLOSE_PENDING", source="bounded_close_intent")
    ledger.transition(close_intent_id, "SUBMITTING", source="bounded_close_pre_submit")
    bound = make_order_link_id(campaign_id, str(entry.get("decision_id") or ""), close_intent_id)
    if order_link_id != bound:
        raise ValueError("close_orderlink_not_bound_to_durable_intent")
    return close_intent_id, order_link_id


def submit_close_after_persist(
    *,
    ledger: DurableOrderLedger,
    reconciler: BybitDemoReconciler,
    writer: Any,
    entry_intent_id: str,
    close_intent_id: str,
    order_link_id: str,
    symbol: str,
    position_side: str,
    qty: str,
    submit_attempts: dict[str, int] | None = None,
) -> dict[str, Any]:
    attempts = submit_attempts if submit_attempts is not None else {}
    record = ledger.get_intent(close_intent_id)
    if record is None:
        return {"ok": False, "reason": "close_intent_missing", "create_order_calls": 0}

    prior_attempts = int(attempts.get(order_link_id) or 0)
    if prior_attempts >= 1:
        recovered = reconcile_submit_unknown(
            ledger=ledger,
            reconciler=reconciler,
            writer=writer,
            order_intent_id=close_intent_id,
            order_link_id=order_link_id,
            symbol=symbol,
        )
        recovered["create_order_calls"] = 0
        recovered["blocked"] = "NO_BLIND_RETRY"
        recovered["close_intent_id"] = close_intent_id
        recovered["close_order_link_id"] = order_link_id
        return recovered

    if str(record.get("state")) != "SUBMITTING":
        return {"ok": False, "reason": "close_intent_not_ready", "create_order_calls": 0}

    create_order_calls = 0
    try:
        create_order_calls = 1
        attempts[order_link_id] = prior_attempts + 1
        resp = writer.close_reduce_only(
            symbol=symbol,
            side=position_side,
            qty=qty,
            order_link_id=order_link_id,
        )
    except Exception as exc:  # noqa: BLE001
        ledger.transition(
            close_intent_id,
            "SUBMIT_UNKNOWN",
            source="bybit_close_error",
            exchange={"reject_reason": type(exc).__name__},
        )
        unknown = reconcile_submit_unknown(
            ledger=ledger,
            reconciler=reconciler,
            writer=writer,
            order_intent_id=close_intent_id,
            order_link_id=order_link_id,
            symbol=symbol,
        )
        unknown["create_order_calls"] = create_order_calls
        unknown["exchange_write_attempt_total"] = create_order_calls
        unknown["close_intent_id"] = close_intent_id
        unknown["submit_error"] = type(exc).__name__
        return unknown

    result = resp.get("result") if isinstance(resp, dict) else {}
    if not isinstance(result, dict):
        result = resp if isinstance(resp, dict) else {}
    ack_id = str(result.get("orderId") or result.get("order_id") or "")
    if ack_id:
        ledger.transition(
            close_intent_id,
            "ACCEPTED",
            source="bybit_close_ack",
            exchange={"order_id": ack_id, "status": "Created"},
        )
    else:
        ledger.transition(close_intent_id, "SUBMIT_UNKNOWN", source="bybit_close_ack_missing_id")
        unknown = reconcile_submit_unknown(
            ledger=ledger,
            reconciler=reconciler,
            writer=writer,
            order_intent_id=close_intent_id,
            order_link_id=order_link_id,
            symbol=symbol,
        )
        unknown["create_order_calls"] = create_order_calls
        unknown["exchange_write_attempt_total"] = create_order_calls
        unknown["close_intent_id"] = close_intent_id
        return unknown

    state = reconciler.reconcile_intent(ledger.get_intent(close_intent_id) or record)
    if state == "FILLED":
        try:
            ledger.transition(close_intent_id, "FILLED", source="bybit_close_fill")
        except ValueError:
            pass
    try:
        ledger.transition(entry_intent_id, "CLOSED", source="bounded_close_complete")
    except ValueError:
        pass
    try:
        ledger.transition(close_intent_id, "CLOSED", source="bounded_close_complete")
    except ValueError:
        pass

    return {
        "ok": True,
        "entry_intent_id": entry_intent_id,
        "close_intent_id": close_intent_id,
        "close_order_link_id": order_link_id,
        "close_order_id": ack_id,
        "bybit_order_id": ack_id,
        "reconciled_state": state,
        "create_order_calls": create_order_calls,
        "exchange_write_attempt_total": create_order_calls,
        "blind_retry": False,
    }


def identify_exchange_triggered_close(
    *,
    writer: Any,
    active: dict[str, Any],
    ledger: DurableOrderLedger | None = None,
) -> dict[str, Any]:
    """Deterministic close identity for TP/SL or external flat — never first-reduceOnly fallback."""
    close_order_id = str(active.get("close_order_id") or "").strip()
    if close_order_id:
        return {"ok": True, "close_order_id": close_order_id, "source": "lifecycle"}

    close_intent_id = str(active.get("close_order_intent_id") or "").strip()
    if close_intent_id and ledger is not None:
        record = ledger.get_intent(close_intent_id)
        if record and record.get("bybit_order_id"):
            return {
                "ok": True,
                "close_order_id": str(record["bybit_order_id"]),
                "source": "durable_close_intent",
            }

    symbol = str(active.get("symbol") or "")
    opened_at = float(active.get("opened_at") or 0.0)
    qty = str(active.get("qty") or "")
    entry_price = str(active.get("actual_entry_price") or active.get("entry_price") or "")
    entry_order_id = str(active.get("entry_order_id") or active.get("bybit_order_id") or "")
    if not symbol or not qty or opened_at <= 0:
        return {"ok": False, "reason": "CLOSE_IDENTITY_HOLD", "hold": True}

    opened_ms = int(opened_at * 1000)
    list_closed = getattr(writer, "list_closed_pnl", None)
    if callable(list_closed):
        fingerprint_matches: list[dict[str, Any]] = []
        for row in list_closed(symbol=symbol, limit=50):
            if not isinstance(row, dict):
                continue
            oid = str(row.get("orderId") or "")
            if not oid or oid == entry_order_id:
                continue
            if str(row.get("qty") or "") != qty:
                continue
            if entry_price and str(row.get("avgEntryPrice") or "") != entry_price:
                continue
            updated_ms = _epoch_ms(row.get("updatedTime") or row.get("createdTime"))
            if updated_ms and updated_ms < opened_ms - 5000:
                continue
            fingerprint_matches.append(row)
        if len(fingerprint_matches) == 1:
            return {
                "ok": True,
                "close_order_id": str(fingerprint_matches[0].get("orderId") or ""),
                "source": "exact_closed_pnl_fingerprint",
            }

    list_exec = getattr(writer, "list_executions", None)
    if callable(list_exec):
        exec_order_ids: list[str] = []
        for row in list_exec(symbol=symbol, limit=50):
            if not isinstance(row, dict):
                continue
            if str(row.get("reduceOnly")).lower() not in {"true", "1"}:
                continue
            exec_ms = _epoch_ms(row.get("execTime"))
            if exec_ms and exec_ms < opened_ms:
                continue
            exec_qty = str(row.get("execQty") or row.get("qty") or "")
            if exec_qty != qty:
                continue
            oid = str(row.get("orderId") or "")
            if oid and oid != entry_order_id:
                exec_order_ids.append(oid)
        unique = list(dict.fromkeys(exec_order_ids))
        if len(unique) == 1:
            return {"ok": True, "close_order_id": unique[0], "source": "exact_execution_identity"}

    return {"ok": False, "reason": "CLOSE_IDENTITY_HOLD", "hold": True}


def _epoch_ms(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        ms = int(float(value))
    except (TypeError, ValueError):
        return None
    if ms < 10_000_000_000:
        ms *= 1000
    return ms
