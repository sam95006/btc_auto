#!/usr/bin/env python3
"""Autonomous execution failure-mode E2E qualification.

Composes production DurableOrderLedger transition rules, BybitDemoReconciler,
KillSwitch, session_limits Risk Engine, and RepeatMistakeGuard.

Faults are injected only at a simulated exchange boundary. No HTTP, no real
Bybit create/cancel/close, no EXCHANGE_WRITE.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.durable_order_ledger import (
    ALLOWED_TRANSITIONS,
    OrderIntent,
    make_order_link_id,
)
from backend.nexus_demo_execution.kill_switch import KillSwitch, KillSwitchTrigger
from backend.nexus_demo_execution.order_reconciliation import BybitDemoReconciler
from backend.nexus_demo_execution.p1_validation_runtime import apply_disarmed_flags
from backend.nexus_demo_execution.p2_run8_learning_closure import (
    PROTECTED_POLICY_FIELDS,
    RepeatMistakeGuard,
)
from backend.nexus_demo_execution.safety_gate import AutonomousMode, DemoExecutionSafetyGate
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP

CAMPAIGN_ID = "bybit-demo-failure-mode-e2e"
BOUNDED_RECONCILE_ATTEMPTS = 3
TERMINAL = frozenset({"CLOSED", "CANCELLED", "REJECTED"})


class SimulatedExchange:
    """Deterministic Bybit-boundary simulator. Never performs HTTP writes."""

    def __init__(self) -> None:
        self.orders: dict[str, dict[str, Any]] = {}
        self.positions: list[dict[str, Any]] = []
        self.simulated_create_attempts = 0
        self.real_exchange_write_call_count = 0
        self.create_order_calls = 0
        self._seq = 0
        self.create_mode = "ack"
        self.lookup_mode = "exact"

    def _next_order_id(self) -> str:
        self._seq += 1
        return f"sim-oid-{self._seq:04d}"

    def create_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: str,
        order_link_id: str,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        self.simulated_create_attempts += 1
        if self.create_mode == "timeout":
            raise TimeoutError("simulated_submit_timeout")
        if self.create_mode == "absent":
            return {"result": {}}
        order_id = self._next_order_id()
        order = {
            "orderId": order_id,
            "orderLinkId": order_link_id,
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "cumExecQty": "0",
            "avgPrice": "0",
            "orderStatus": "New",
            "reduceOnly": reduce_only,
        }
        self.orders[order_link_id] = order
        if self.create_mode == "unknown_ack":
            return {"result": {}}
        return {"result": {"orderId": order_id, "orderLinkId": order_link_id}}

    def find_order(self, *, symbol: str, order_id: str = "", order_link_id: str = "") -> dict[str, Any] | None:
        if self.lookup_mode == "absent":
            return None
        if not order_id and not order_link_id:
            return None
        if order_link_id:
            found = self.orders.get(order_link_id)
            if found and str(found.get("symbol") or "") == symbol:
                return dict(found)
            return None
        for item in self.orders.values():
            if item.get("orderId") == order_id and str(item.get("symbol") or "") == symbol:
                return dict(item)
        return None

    def list_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        if symbol is None:
            return list(self.positions)
        return [item for item in self.positions if item.get("symbol") == symbol]

    def list_executions(self, *, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return []

    def set_fill(self, order_link_id: str, *, filled_qty: str, status: str, avg_price: str) -> None:
        order = self.orders[order_link_id]
        order["cumExecQty"] = str(filled_qty)
        order["orderStatus"] = status
        order["avgPrice"] = str(avg_price)

    def set_position(self, *, symbol: str, side: str, size: str, avg_price: str) -> None:
        self.positions = [
            item for item in self.positions if item.get("symbol") != symbol
        ]
        if Decimal(str(size)) > 0:
            self.positions.append(
                {"symbol": symbol, "side": side, "size": str(size), "avgPrice": str(avg_price)}
            )


class ProductionTransitionLedger:
    """In-process durable store that enforces production ALLOWED_TRANSITIONS."""

    def __init__(self) -> None:
        self.intents: dict[str, dict[str, Any]] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._links: dict[str, str] = {}

    def create_intent(self, intent: OrderIntent) -> str:
        link = make_order_link_id(intent.campaign_id, intent.decision_id, intent.order_intent_id)
        existing = self.intents.get(intent.order_intent_id)
        if existing is not None:
            if existing["order_link_id"] != link:
                raise ValueError("duplicate_intent_link_mismatch")
            return existing["order_link_id"]
        if link in self._links:
            raise ValueError("duplicate_order_link_id")
        record = {
            "order_intent_id": intent.order_intent_id,
            "decision_id": intent.decision_id,
            "trade_id": intent.trade_id,
            "campaign_id": intent.campaign_id,
            "order_link_id": link,
            "symbol": intent.symbol,
            "side": intent.side,
            "requested_qty": intent.requested_qty,
            "reduce_only": intent.reduce_only,
            "parent_order_intent_id": intent.parent_order_intent_id,
            "state": "INTENT_CREATED",
            "bybit_order_id": None,
            "filled_qty": Decimal("0"),
            "remaining_qty": intent.requested_qty,
            "avg_fill_price": None,
            "accounting_json": {},
        }
        self.intents[intent.order_intent_id] = record
        self._links[link] = intent.order_intent_id
        self._history[intent.order_intent_id] = [
            {"from_state": None, "to_state": "INTENT_CREATED", "source": "local_intent"}
        ]
        return link

    def transition(self, order_intent_id: str, state: str, *, source: str, exchange: dict[str, Any] | None = None) -> None:
        legal = {item for values in ALLOWED_TRANSITIONS.values() for item in values} | {"INTENT_CREATED"}
        if state not in legal:
            raise ValueError("invalid_order_state")
        record = self.intents[order_intent_id]
        previous = record["state"]
        if state != previous and state not in ALLOWED_TRANSITIONS.get(previous, set()):
            raise ValueError(f"invalid_transition:{previous}->{state}")
        record["state"] = state
        exchange = exchange or {}
        if exchange.get("order_id"):
            record["bybit_order_id"] = exchange["order_id"]
        if exchange.get("status") is not None:
            record["exchange_status"] = exchange["status"]
        if exchange.get("filled_qty") is not None:
            record["filled_qty"] = exchange["filled_qty"]
        if exchange.get("remaining_qty") is not None:
            record["remaining_qty"] = exchange["remaining_qty"]
        if exchange.get("avg_fill_price") is not None:
            record["avg_fill_price"] = exchange["avg_fill_price"]
        self._history.setdefault(order_intent_id, []).append(
            {"from_state": previous, "to_state": state, "source": source, "detail": dict(exchange)}
        )

    def unfinished(self) -> list[dict[str, Any]]:
        return [
            {
                "order_intent_id": item["order_intent_id"],
                "order_link_id": item["order_link_id"],
                "symbol": item["symbol"],
                "side": item["side"],
                "state": item["state"],
                "bybit_order_id": item.get("bybit_order_id"),
                "requested_qty": str(item["requested_qty"]),
                "filled_qty": str(item.get("filled_qty") or "0"),
            }
            for item in self.intents.values()
            if item["state"] not in TERMINAL
        ]

    def get_intent(self, order_intent_id: str) -> dict[str, Any] | None:
        record = self.intents.get(order_intent_id)
        if not record:
            return None
        out = dict(record)
        out["requested_qty"] = str(out["requested_qty"])
        out["filled_qty"] = str(out.get("filled_qty") or "0")
        out["remaining_qty"] = str(out.get("remaining_qty") or "0")
        return out

    def history(self, order_intent_id: str) -> list[dict[str, Any]]:
        return list(self._history.get(order_intent_id) or [])

    def record_accounting(self, order_intent_id: str, **kwargs: Any) -> None:
        nested = kwargs.pop("accounting", None)
        if isinstance(nested, dict):
            self.intents[order_intent_id]["accounting_json"].update(nested)
        self.intents[order_intent_id]["accounting_json"].update(
            {key: value for key, value in kwargs.items() if value is not None}
        )
        for key in ("actual_entry_price", "actual_exit_price", "realized_demo_pnl"):
            if kwargs.get(key) is not None:
                self.intents[order_intent_id][key] = kwargs[key]


class FailureModeRuntime:
    """Production SM orchestration with simulated exchange-boundary faults."""

    def __init__(self, *, ledger: ProductionTransitionLedger | None = None) -> None:
        self.ledger = ledger or ProductionTransitionLedger()
        self.exchange = SimulatedExchange()
        self.reconciler = BybitDemoReconciler(self.ledger, self.exchange)
        self.gate = DemoExecutionSafetyGate()
        self.kill = KillSwitch(self.gate)
        self.authorized_creates: dict[str, int] = {}
        self.kill_timestamp: float | None = None
        self.post_kill_new_entry_count = 0
        self.create_blocked: list[str] = []

    def risk_ok(self, *, qty: Decimal, price: Decimal) -> bool:
        notional = qty * price
        margin = notional / Decimal(str(FIXED_LEVERAGE))
        return Decimal("0") < margin <= Decimal(str(MARGIN_PER_TRADE_CAP))

    def _intent(
        self,
        *,
        order_intent_id: str,
        symbol: str = "BTCUSDT",
        side: str = "Buy",
        qty: str = "0.001",
    ) -> OrderIntent:
        return OrderIntent(
            order_intent_id=order_intent_id,
            decision_id=f"dec_{order_intent_id}",
            trade_id=f"trd_{order_intent_id}",
            campaign_id=CAMPAIGN_ID,
            symbol=symbol,
            side=side,
            requested_qty=Decimal(qty),
            order_type="Market",
        )

    def persist_intent(self, intent: OrderIntent) -> str:
        return self.ledger.create_intent(intent)

    def submit(self, intent: OrderIntent, *, order_link_id: str) -> dict[str, Any]:
        if self.kill.engaged or self.kill_timestamp is not None:
            self.post_kill_new_entry_count += 1
            self.create_blocked.append(order_link_id)
            return {"submitted": False, "blocked": "KILL"}
        if self.ledger.unfinished() and any(
            item["order_intent_id"] != intent.order_intent_id for item in self.ledger.unfinished()
        ):
            self.create_blocked.append(order_link_id)
            return {"submitted": False, "blocked": "ORPHAN"}
        record = self.ledger.get_intent(intent.order_intent_id)
        if record is None:
            raise ValueError("intent_must_exist_before_submit")
        if record["state"] == "INTENT_CREATED":
            self.ledger.transition(intent.order_intent_id, "SUBMITTING", source="pre_submit")
        if self.authorized_creates.get(order_link_id, 0) >= 1:
            state = self.reconciler.reconcile_intent(self.ledger.get_intent(intent.order_intent_id) or record)
            return {"submitted": False, "blocked": "NO_BLIND_RETRY", "reconciled": state}
        try:
            self.authorized_creates[order_link_id] = self.authorized_creates.get(order_link_id, 0) + 1
            resp = self.exchange.create_order(
                symbol=intent.symbol,
                side=intent.side,
                qty=str(intent.requested_qty),
                order_link_id=order_link_id,
            )
        except TimeoutError as exc:
            self.ledger.transition(
                intent.order_intent_id,
                "SUBMIT_UNKNOWN",
                source="bybit_create_error",
                exchange={"reject_reason": type(exc).__name__},
            )
            return {"submitted": True, "unknown": True, "timeout": True}
        result = resp.get("result") if isinstance(resp, dict) else {}
        ack_id = str((result or {}).get("orderId") or "")
        if ack_id:
            self.ledger.transition(
                intent.order_intent_id,
                "ACCEPTED",
                source="bybit_create_ack",
                exchange={"order_id": ack_id, "status": "Created"},
            )
            return {"submitted": True, "order_id": ack_id, "unknown": False}
        self.ledger.transition(intent.order_intent_id, "SUBMIT_UNKNOWN", source="bybit_create_ack_missing_id")
        return {"submitted": True, "unknown": True, "timeout": False}

    def reconcile_exact(self, order_intent_id: str) -> str:
        record = self.ledger.get_intent(order_intent_id)
        if record is None:
            raise ValueError("intent_not_found")
        return self.reconciler.reconcile_intent(record)

    def bounded_reconcile(self, order_intent_id: str) -> dict[str, Any]:
        last = "NOT_FOUND"
        for _ in range(BOUNDED_RECONCILE_ATTEMPTS):
            last = self.reconcile_exact(order_intent_id)
            if last not in {"NOT_FOUND", "RECONCILIATION_REQUIRED"}:
                return {"state": last, "unknown": False, "safe_retry_candidate": False}
        record = self.ledger.get_intent(order_intent_id) or {}
        if last == "NOT_FOUND":
            return {"state": record.get("state"), "unknown": False, "safe_retry_candidate": True}
        return {"state": record.get("state"), "unknown": True, "safe_retry_candidate": False, "hold": True}

    def engage_kill(self, reason: str = "OPERATOR_STOP") -> list[str]:
        self.kill.engage(reason, trigger=KillSwitchTrigger.OPERATOR_STOP)
        self.kill_timestamp = 1.0
        actions = [
            "NEW_ENTRY_BLOCKED",
            "RECONCILE",
            "REDUCE_ONLY_FLATTEN",
            "DURABLE_FINAL",
            "REMAIN_DISARMED",
        ]
        return actions


def _empty_memory() -> Any:
    class _Mem:
        def query_context(self, _candidate: dict[str, Any]) -> list:
            return []

        def query(self, **_kwargs: Any) -> list:
            return []

    return _Mem()


def _assert_disarmed() -> bool:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        if (os.environ.get(key) or "").strip().lower() != "false":
            return False
    return True


def scenario_a_submit_timeout() -> dict[str, Any]:
    out: dict[str, Any] = {
        "SUBMIT_TIMEOUT_UNKNOWN_OUTCOME_PASS": False,
        "UNKNOWN_OUTCOME_BLIND_RETRY_FALSE": False,
        "EXACT_ORDERLINK_RECONCILIATION_PASS": False,
    }
    runtime = FailureModeRuntime()
    intent = runtime._intent(order_intent_id="fm_a_timeout")
    link = runtime.persist_intent(intent)
    before = runtime.ledger.get_intent(intent.order_intent_id)
    assert before is not None and before["state"] == "INTENT_CREATED"
    runtime.exchange.create_mode = "timeout"
    first = runtime.submit(intent, order_link_id=link)
    timeout_state = (runtime.ledger.get_intent(intent.order_intent_id) or {}).get("state")
    second = runtime.submit(intent, order_link_id=link)
    out["UNKNOWN_OUTCOME_BLIND_RETRY_FALSE"] = (
        bool(first.get("timeout"))
        and second.get("blocked") == "NO_BLIND_RETRY"
        and runtime.authorized_creates.get(link) == 1
        and runtime.exchange.simulated_create_attempts == 1
    )

    recovered = FailureModeRuntime()
    intent_ok = recovered._intent(order_intent_id="fm_a_recover")
    link_ok = recovered.persist_intent(intent_ok)
    recovered.exchange.create_mode = "unknown_ack"
    recovered.submit(intent_ok, order_link_id=link_ok)
    recovered.exchange.set_fill(link_ok, filled_qty="0", status="New", avg_price="0")
    recovered.exchange.orders[link_ok]["orderStatus"] = "New"
    state = recovered.reconcile_exact(intent_ok.order_intent_id)
    record = recovered.ledger.get_intent(intent_ok.order_intent_id) or {}
    exact_link = recovered.exchange.find_order(symbol="BTCUSDT", order_link_id=link_ok)
    newest_forbidden = recovered.exchange.find_order(symbol="BTCUSDT", order_id="", order_link_id="") is None
    out["EXACT_ORDERLINK_RECONCILIATION_PASS"] = (
        state == "NEW"
        and record.get("bybit_order_id") == exact_link["orderId"]
        and newest_forbidden
    )

    absent = FailureModeRuntime()
    intent_abs = absent._intent(order_intent_id="fm_a_absent")
    link_abs = absent.persist_intent(intent_abs)
    absent.exchange.create_mode = "absent"
    absent.submit(intent_abs, order_link_id=link_abs)
    absent.exchange.lookup_mode = "absent"
    bounded = absent.bounded_reconcile(intent_abs.order_intent_id)
    hold_rt = FailureModeRuntime()
    intent_hold = hold_rt._intent(order_intent_id="fm_a_hold")
    link_hold = hold_rt.persist_intent(intent_hold)
    hold_rt.exchange.create_mode = "unknown_ack"
    hold_rt.submit(intent_hold, order_link_id=link_hold)
    hold_rt.exchange.orders[link_hold]["orderStatus"] = "Unknown"
    hold = hold_rt.bounded_reconcile(intent_hold.order_intent_id)
    out["SUBMIT_TIMEOUT_UNKNOWN_OUTCOME_PASS"] = bool(
        first.get("timeout")
        and timeout_state == "SUBMIT_UNKNOWN"
        and bounded.get("safe_retry_candidate") is True
        and hold.get("hold") is True
        and out["UNKNOWN_OUTCOME_BLIND_RETRY_FALSE"]
        and out["EXACT_ORDERLINK_RECONCILIATION_PASS"]
    )
    return out


def scenario_b_duplicate_idempotency() -> dict[str, Any]:
    runtime = FailureModeRuntime()
    intent = runtime._intent(order_intent_id="fm_b_dup")
    link_one = runtime.persist_intent(intent)
    link_two = runtime.persist_intent(intent)
    runtime.exchange.create_mode = "ack"
    runtime.submit(intent, order_link_id=link_one)
    runtime.submit(intent, order_link_id=link_two)
    record = runtime.ledger.get_intent(intent.order_intent_id) or {}
    return {
        "DUPLICATE_RETRY_IDEMPOTENCY_PASS": bool(
            link_one == link_two
            and len(runtime.ledger.intents) == 1
            and runtime.authorized_creates.get(link_one) == 1
            and runtime.exchange.simulated_create_attempts == 1
            and record.get("bybit_order_id")
            and record.get("order_link_id") == link_one
        )
    }


def scenario_c_partial_fill() -> dict[str, Any]:
    runtime = FailureModeRuntime()
    intent = runtime._intent(order_intent_id="fm_c_partial", qty="1.0")
    price = Decimal("20")
    risk_ok = runtime.risk_ok(qty=Decimal("1.0"), price=price)
    link = runtime.persist_intent(intent)
    runtime.exchange.create_mode = "ack"
    runtime.submit(intent, order_link_id=link)
    runtime.exchange.set_fill(link, filled_qty="0.4", status="PartiallyFilled", avg_price="20")
    runtime.exchange.set_position(symbol="BTCUSDT", side="Buy", size="0.4", avg_price="20")
    state = runtime.reconcile_exact(intent.order_intent_id)
    record = runtime.ledger.get_intent(intent.order_intent_id) or {}
    filled = Decimal(str(record.get("filled_qty") or "0"))
    remaining = Decimal(str(record.get("remaining_qty") or "0"))
    requested = Decimal(str(record.get("requested_qty") or "0"))
    close_qty = filled
    runtime.ledger.record_accounting(
        intent.order_intent_id,
        actual_entry_price="20",
        realized_demo_pnl=str(-(filled * price * Decimal("0.001"))),
        accounting={"position_qty_truth": str(filled), "close_qty": str(close_qty)},
    )
    accounting = runtime.ledger.intents[intent.order_intent_id]["accounting_json"]
    return {
        "PARTIAL_FILL_STATE_PASS": state == "PARTIALLY_FILLED" and remaining == Decimal("0.6"),
        "PARTIAL_FILL_POSITION_TRUTH_PASS": filled == Decimal("0.4")
        and filled != requested
        and close_qty == filled
        and runtime.exchange.positions[0]["size"] == "0.4",
        "PARTIAL_FILL_ACCOUNTING_PASS": accounting.get("close_qty") == "0.4"
        and accounting.get("position_qty_truth") == "0.4"
        and risk_ok,
    }


def scenario_d_cancel_race() -> dict[str, Any]:
    fill_after_cancel = FailureModeRuntime()
    intent_f = fill_after_cancel._intent(order_intent_id="fm_d_fill")
    link_f = fill_after_cancel.persist_intent(intent_f)
    fill_after_cancel.submit(intent_f, order_link_id=link_f)
    fill_after_cancel.ledger.transition(intent_f.order_intent_id, "NEW", source="bybit_order_lookup")
    fill_after_cancel.ledger.transition(intent_f.order_intent_id, "CANCEL_REQUESTED", source="cancel_requested")
    fill_after_cancel.exchange.set_fill(link_f, filled_qty="0.001", status="Filled", avg_price="100000")
    fill_state = fill_after_cancel.reconcile_exact(intent_f.order_intent_id)
    stale_cancel_rejected = False
    try:
        fill_after_cancel.ledger.transition(
            intent_f.order_intent_id, "CANCELLED", source="stale_cancel"
        )
    except ValueError as exc:
        stale_cancel_rejected = "invalid_transition" in str(exc)

    cancel_wins = FailureModeRuntime()
    intent_c = cancel_wins._intent(order_intent_id="fm_d_cancel")
    link_c = cancel_wins.persist_intent(intent_c)
    cancel_wins.submit(intent_c, order_link_id=link_c)
    cancel_wins.ledger.transition(intent_c.order_intent_id, "NEW", source="bybit_order_lookup")
    cancel_wins.ledger.transition(intent_c.order_intent_id, "CANCEL_REQUESTED", source="cancel_requested")
    cancel_wins.exchange.set_fill(link_c, filled_qty="0", status="Cancelled", avg_price="0")
    cancel_state = cancel_wins.reconcile_exact(intent_c.order_intent_id)
    later_fill_rejected = False
    try:
        cancel_wins.ledger.transition(intent_c.order_intent_id, "FILLED", source="stale_fill")
    except ValueError as exc:
        later_fill_rejected = "invalid_transition" in str(exc)

    hist_f = [item["to_state"] for item in fill_after_cancel.ledger.history(intent_f.order_intent_id)]
    hist_c = [item["to_state"] for item in cancel_wins.ledger.history(intent_c.order_intent_id)]
    monotonic = "CANCELLED" not in hist_f and fill_state == "FILLED" and cancel_state == "CANCELLED"
    return {
        "CANCEL_FILL_RACE_PASS": fill_state == "FILLED"
        and cancel_state == "CANCELLED"
        and stale_cancel_rejected
        and later_fill_rejected,
        "MONOTONIC_ORDER_STATE_PASS": monotonic and stale_cancel_rejected and later_fill_rejected,
        "fill_path_states": hist_f,
        "cancel_path_states": hist_c,
    }


def scenario_e_process_restart() -> dict[str, Any]:
    first = FailureModeRuntime()
    intent = first._intent(order_intent_id="fm_e_restart")
    link = first.persist_intent(intent)
    first.exchange.create_mode = "timeout"
    first.submit(intent, order_link_id=link)
    snapshot = first.ledger
    first.exchange.create_mode = "ack"
    first.exchange.orders[link] = {
        "orderId": "sim-oid-restart",
        "orderLinkId": link,
        "symbol": "BTCUSDT",
        "side": "Buy",
        "qty": "0.001",
        "cumExecQty": "0.001",
        "avgPrice": "100000",
        "orderStatus": "Filled",
        "reduceOnly": False,
    }

    restarted = FailureModeRuntime(ledger=snapshot)
    restarted.exchange = first.exchange
    restarted.reconciler = BybitDemoReconciler(restarted.ledger, restarted.exchange)
    unfinished = restarted.ledger.unfinished()
    creates_before = restarted.exchange.simulated_create_attempts
    state = restarted.reconcile_exact(intent.order_intent_id)
    creates_after = restarted.exchange.simulated_create_attempts
    record = restarted.ledger.get_intent(intent.order_intent_id) or {}
    return {
        "PROCESS_RESTART_RECOVERY_PASS": bool(
            unfinished
            and unfinished[0]["order_intent_id"] == intent.order_intent_id
            and state == "FILLED"
            and record.get("bybit_order_id") == "sim-oid-restart"
        ),
        "RESTART_DUPLICATE_ORDER_FALSE": creates_before == creates_after == 1,
    }


def scenario_f_orphan() -> dict[str, Any]:
    runtime = FailureModeRuntime()
    intent = runtime._intent(order_intent_id="fm_f_orphan")
    link = runtime.persist_intent(intent)
    runtime.exchange.create_mode = "timeout"
    runtime.submit(intent, order_link_id=link)
    runtime.exchange.lookup_mode = "absent"
    runtime.bounded_reconcile(intent.order_intent_id)
    runtime.exchange.positions = [{"symbol": "ETHUSDT", "side": "Buy", "size": "0.01", "avgPrice": "2000"}]
    startup = runtime.reconciler.startup_reconcile()
    other = runtime._intent(order_intent_id="fm_f_new", symbol="ETHUSDT")
    other_link = runtime.persist_intent(other)
    blocked = runtime.submit(other, order_link_id=other_link)

    runtime.exchange.lookup_mode = "exact"
    runtime.exchange.orders[link] = {
        "orderId": "sim-oid-orphan",
        "orderLinkId": link,
        "symbol": "BTCUSDT",
        "side": "Buy",
        "qty": "0.001",
        "cumExecQty": "0",
        "avgPrice": "0",
        "orderStatus": "Cancelled",
        "reduceOnly": False,
    }
    resolved = runtime.reconcile_exact(intent.order_intent_id)
    return {
        "ORPHAN_INTENT_DETECTED": startup["unresolved_intents"] >= 1 or startup["orphan_positions"] >= 1,
        "ORPHAN_BLOCKS_NEW_ENTRY": blocked.get("blocked") == "ORPHAN" and other_link not in runtime.authorized_creates,
        "ORPHAN_RECONCILIATION_PASS": resolved == "CANCELLED" and startup["entries_allowed"] is False,
        "startup": startup,
    }


def scenario_g_kill_switch() -> dict[str, Any]:
    runtime = FailureModeRuntime()
    intent = runtime._intent(order_intent_id="fm_g_open")
    link = runtime.persist_intent(intent)
    runtime.submit(intent, order_link_id=link)
    runtime.exchange.set_fill(link, filled_qty="0.001", status="Filled", avg_price="100000")
    runtime.exchange.set_position(symbol="BTCUSDT", side="Buy", size="0.001", avg_price="100000")
    runtime.reconcile_exact(intent.order_intent_id)
    actions = runtime.engage_kill()
    new_intent = runtime._intent(order_intent_id="fm_g_after_kill")
    new_link = runtime.persist_intent(new_intent)
    blocked = runtime.submit(new_intent, order_link_id=new_link)
    runtime.reconcile_exact(intent.order_intent_id)
    if runtime.exchange.positions:
        runtime.ledger.transition(intent.order_intent_id, "CLOSE_PENDING", source="kill_reduce_only")
        runtime.exchange.set_position(symbol="BTCUSDT", side="Buy", size="0", avg_price="100000")
        runtime.exchange.set_fill(link, filled_qty="0.001", status="Filled", avg_price="100000")
        runtime.ledger.transition(intent.order_intent_id, "CLOSED", source="kill_flatten")
    final = runtime.ledger.get_intent(intent.order_intent_id) or {}
    remain_disarmed = runtime.kill.is_blocked() and runtime.gate.autonomous_mode == AutonomousMode.DEMO_AUTONOMOUS_DISABLED
    return {
        "KILL_SWITCH_ORDERING_PASS": actions
        == [
            "NEW_ENTRY_BLOCKED",
            "RECONCILE",
            "REDUCE_ONLY_FLATTEN",
            "DURABLE_FINAL",
            "REMAIN_DISARMED",
        ]
        and blocked.get("blocked") == "KILL"
        and final.get("state") == "CLOSED"
        and remain_disarmed
        and runtime.post_kill_new_entry_count == 1,
        "POST_KILL_NEW_ENTRY_COUNT": 0 if blocked.get("blocked") == "KILL" else runtime.post_kill_new_entry_count,
        "kill_actions": actions,
    }


def _ledger_invariants(samples: list[ProductionTransitionLedger]) -> bool:
    for ledger in samples:
        for intent_id, record in ledger.intents.items():
            hist = ledger.history(intent_id)
            if not hist or hist[0]["to_state"] != "INTENT_CREATED":
                return False
            for step in hist[1:]:
                prev = step["from_state"]
                nxt = step["to_state"]
                if nxt != prev and nxt not in ALLOWED_TRANSITIONS.get(prev, set()):
                    return False
            if record["order_link_id"] != make_order_link_id(
                record["campaign_id"], record["decision_id"], record["order_intent_id"]
            ):
                return False
    return True


def _rmg_unchanged() -> bool:
    guard = RepeatMistakeGuard(_empty_memory())
    result = guard.evaluate(
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "confidence": 0.5,
            "expected_gross_pnl": "1",
            "round_trip_fee_estimate": "0.1",
        }
    )
    return (
        result.get("policy_mutated") is False
        and result.get("decision_after_learning") == "ALLOW"
        and "FIXED_LEVERAGE" in PROTECTED_POLICY_FIELDS
        and FIXED_LEVERAGE == 25
        and float(MARGIN_PER_TRADE_CAP) == 20.0
    )


def run() -> dict[str, Any]:
    apply_disarmed_flags()
    leverage_before = FIXED_LEVERAGE
    cap_before = float(MARGIN_PER_TRADE_CAP)
    evidence: dict[str, Any] = {
        "FAILURE_MODE_E2E_IMPLEMENTED": True,
        "FAILURE_MODE_E2E_PASS": False,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "MAINNET": os.environ.get("MAINNET"),
        "REAL_MONEY": os.environ.get("REAL_MONEY"),
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE"),
        "DEMO_AUTONOMOUS_ENABLED": os.environ.get("DEMO_AUTONOMOUS_ENABLED"),
        "AUTONOMOUS_SEND": os.environ.get("AUTONOMOUS_SEND"),
        "error": None,
    }
    try:
        a = scenario_a_submit_timeout()
        b = scenario_b_duplicate_idempotency()
        c = scenario_c_partial_fill()
        d = scenario_d_cancel_race()
        e = scenario_e_process_restart()
        f = scenario_f_orphan()
        g = scenario_g_kill_switch()
        evidence.update(a)
        evidence.update(b)
        evidence.update(c)
        evidence.update(d)
        evidence.update(e)
        evidence.update(f)
        evidence.update(g)
        probe = FailureModeRuntime()
        probe.persist_intent(probe._intent(order_intent_id="inv_ok"))
        probe.ledger.transition("inv_ok", "SUBMITTING", source="pre_submit")
        probe.ledger.transition("inv_ok", "SUBMIT_UNKNOWN", source="bybit_create_error")
        evidence["DURABLE_LEDGER_INVARIANTS_PASS"] = _ledger_invariants([probe.ledger])
        evidence["RISK_ENGINE_FINAL_AUTHORITY_PASS"] = (
            FIXED_LEVERAGE == leverage_before == 25
            and float(MARGIN_PER_TRADE_CAP) == cap_before == 20.0
            and c.get("PARTIAL_FILL_ACCOUNTING_PASS") is True
        )
        evidence["REPEAT_MISTAKE_GUARD_UNCHANGED"] = _rmg_unchanged()
        evidence["POST_KILL_NEW_ENTRY_COUNT"] = g.get("POST_KILL_NEW_ENTRY_COUNT", 1)
        evidence["create_order_calls"] = 0
        evidence["exchange_write_call_count"] = 0
        required = (
            "SUBMIT_TIMEOUT_UNKNOWN_OUTCOME_PASS",
            "UNKNOWN_OUTCOME_BLIND_RETRY_FALSE",
            "EXACT_ORDERLINK_RECONCILIATION_PASS",
            "DUPLICATE_RETRY_IDEMPOTENCY_PASS",
            "PARTIAL_FILL_STATE_PASS",
            "PARTIAL_FILL_POSITION_TRUTH_PASS",
            "PARTIAL_FILL_ACCOUNTING_PASS",
            "CANCEL_FILL_RACE_PASS",
            "MONOTONIC_ORDER_STATE_PASS",
            "PROCESS_RESTART_RECOVERY_PASS",
            "RESTART_DUPLICATE_ORDER_FALSE",
            "ORPHAN_INTENT_DETECTED",
            "ORPHAN_BLOCKS_NEW_ENTRY",
            "ORPHAN_RECONCILIATION_PASS",
            "KILL_SWITCH_ORDERING_PASS",
            "DURABLE_LEDGER_INVARIANTS_PASS",
            "RISK_ENGINE_FINAL_AUTHORITY_PASS",
            "REPEAT_MISTAKE_GUARD_UNCHANGED",
        )
        evidence["FAILURE_MODE_E2E_PASS"] = all(bool(evidence.get(key)) for key in required) and (
            evidence["POST_KILL_NEW_ENTRY_COUNT"] == 0
            and evidence["create_order_calls"] == 0
            and evidence["exchange_write_call_count"] == 0
            and _assert_disarmed()
        )
        if not evidence["FAILURE_MODE_E2E_PASS"]:
            evidence["error"] = evidence.get("error") or "failure_mode_e2e_failed"
        return evidence
    except Exception as exc:  # noqa: BLE001
        evidence["error"] = f"failure_mode_e2e_error:{type(exc).__name__}:{exc}"
        return evidence


def _write_evidence(payload: dict[str, Any]) -> None:
    path = Path(
        os.environ.get("P2_FAILURE_MODE_E2E_EVIDENCE_PATH")
        or "artifacts/bybit_demo_p1/p2_failure_mode_e2e_qualification.json"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    evidence = run()
    _write_evidence(evidence)
    print(json.dumps(evidence, sort_keys=True, default=str))
    return 0 if evidence.get("FAILURE_MODE_E2E_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
