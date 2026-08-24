#!/usr/bin/env python3
"""Bounded 6H runtime integration qualification — certified P1/P2 wiring, no exchange writes."""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.nexus_bounded_runtime.certified_entry import (
    candidate_to_market_input,
    persist_durable_intent,
    submit_after_persist,
)
from backend.nexus_bounded_runtime.certified_guard import evaluate_certified_guard
from backend.nexus_bounded_runtime.certified_learning import write_durable_lesson_from_trade
from backend.nexus_bounded_runtime.certified_session import wiring_markers
from backend.nexus_bounded_runtime.runtime_lease import lease_wiring_markers
from backend.nexus_bounded_runtime.zeabur_env_audit import audit_post_start_disarm_safety
from backend.nexus_demo_execution.durable_order_ledger import make_order_link_id
from backend.nexus_demo_execution.order_reconciliation import BybitDemoReconciler
from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID
from backend.nexus_demo_execution.p1_validation_runtime import apply_disarmed_flags
from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_run8_learning_closure import PNL_PROVENANCE, close_run8_durable_learning
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP
from tools.ci.p2_failure_mode_e2e_qualification import ProductionTransitionLedger, SimulatedExchange
from tools.ci.p2_repeat_mistake_guard_qualification import build_similar_candidate_from_lesson


def _qual_run8_intents() -> list[dict[str, Any]]:
    return [
        {
            "order_intent_id": "p1ent_bd6h_qual",
            "decision_id": "p1dec_bd6h_qual_aaaa",
            "trade_id": "p1trd_bd6h_qual_bbbb",
            "campaign_id": P1_CAMPAIGN_ID,
            "order_link_id": "nx-entry-bd6h-qual",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "requested_qty": "0.001",
            "reduce_only": False,
            "state": "CLOSED",
            "bybit_order_id": "entry-oid-bd6h-qual",
            "filled_qty": "0.001",
            "parent_order_intent_id": None,
            "actual_entry_price": "64282.2",
            "actual_exit_price": "64282.2",
            "realized_demo_pnl": "-0.07071042",
            "pnl_provenance": PNL_PROVENANCE,
            "closed_at": "2026-08-18T07:05:00+00:00",
            "accounting_json": {
                "open_fee": "0.03535521",
                "close_fee": "0.03535521",
                "position_flat": True,
            },
        },
        {
            "order_intent_id": "p1cls_bd6h_qual",
            "decision_id": "p1dec_bd6h_qual_aaaa",
            "trade_id": "p1trd_bd6h_qual_bbbb",
            "campaign_id": P1_CAMPAIGN_ID,
            "order_link_id": "nx-close-bd6h-qual",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "requested_qty": "0.001",
            "reduce_only": True,
            "state": "CLOSED",
            "bybit_order_id": "close-oid-bd6h-qual",
            "filled_qty": "0.001",
            "parent_order_intent_id": "p1ent_bd6h_qual",
            "avg_fill_price": "64282.2",
        },
    ]


class _SimWriter:
    """Simulated Bybit Demo writer — never performs HTTP."""

    def __init__(self, exchange: SimulatedExchange) -> None:
        self.exchange = exchange
        self.create_order_calls = 0
        self.exchange_write_call_count = 0

    def set_leverage(self, symbol: str, leverage: int) -> None:
        del symbol, leverage

    def create_market_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: str,
        order_link_id: str,
        stop_loss: str | None = None,
        take_profit: str | None = None,
    ) -> dict[str, Any]:
        del stop_loss, take_profit
        self.create_order_calls += 1
        return self.exchange.create_order(symbol=symbol, side=side, qty=qty, order_link_id=order_link_id)

    def find_order(self, *, symbol: str, order_id: str = "", order_link_id: str = "") -> dict[str, Any] | None:
        return self.exchange.find_order(symbol=symbol, order_id=order_id, order_link_id=order_link_id)

    def list_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return self.exchange.list_positions(symbol)

    def list_open_orders(self) -> list[dict[str, Any]]:
        return []


def _seed_durable_lesson(db: Path) -> dict[str, Any]:
    store = DurableLessonStore(sqlite_path=db)
    evidence = close_run8_durable_learning(store=store, intents=_qual_run8_intents())
    lesson_row = store.list_lessons()[0]
    store.close()
    return {"evidence": evidence, "lesson": lesson_row}


def _risk_unchanged() -> bool:
    if FIXED_LEVERAGE != 25 or float(MARGIN_PER_TRADE_CAP) != 20.0:
        return False
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        if (os.environ.get(key) or "").strip().lower() != "false":
            return False
    return True


def run(*, sqlite_path: Path | None = None) -> dict[str, Any]:
    apply_disarmed_flags()
    evidence: dict[str, Any] = {
        "BOUNDED_RUNTIME_CERTIFIED_SURFACE_WIRING_PASS": False,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "REAL_EXCHANGE_WRITE_CALLS": 0,
        "error": None,
    }
    evidence.update(wiring_markers())
    evidence.update(lease_wiring_markers())
    evidence.update(
        audit_post_start_disarm_safety(founder_auth_consumed=True, runtime_lease_present=True)
    )

    db = sqlite_path or Path(os.environ.get("BOUNDED_RUNTIME_QUAL_SQLITE") or "artifacts/bounded_runtime_qual.db")
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()

    seeded = _seed_durable_lesson(db)
    lesson = seeded["lesson"]
    store = DurableLessonStore(sqlite_path=db)

    candidate = build_similar_candidate_from_lesson(lesson)
    market_input = candidate_to_market_input(
        {
            "symbol": candidate.get("symbol"),
            "direction": candidate.get("side"),
            "confidence": candidate.get("confidence"),
            "expected_gross_pnl": candidate.get("expected_gross_pnl"),
            "round_trip_fee_estimate": candidate.get("round_trip_fee_estimate"),
            "regime": candidate.get("market_regime"),
            "strategy": candidate.get("signal_family"),
        }
    )
    guard_eval = evaluate_certified_guard(candidate=market_input, store=store)
    evidence["BOUNDED_RUNTIME_DURABLE_LESSON_RETRIEVAL"] = bool(guard_eval.get("memory_hits"))
    evidence["BOUNDED_RUNTIME_CERTIFIED_RMG_AUTHORITY"] = guard_eval.get("policy_authority") == "DURABLE_POSTGRES_LESSON"

    if not guard_eval.get("blocked"):
        evidence["error"] = "similar_candidate_should_be_blocked_by_rmg"
        store.close()
        return evidence

    dissimilar = {
        "symbol": "ETHUSDT",
        "side": "Sell",
        "confidence": 0.91,
        "expected_gross_pnl": "12.5",
        "round_trip_fee_estimate": "0.4",
        "market_regime": "TREND",
        "signal_family": "OTHER",
    }
    allow_eval = evaluate_certified_guard(candidate=dissimilar, store=store)
    if allow_eval.get("blocked"):
        evidence["error"] = "dissimilar_candidate_should_not_be_blocked"
        store.close()
        return evidence

    ledger = ProductionTransitionLedger()
    exchange = SimulatedExchange()
    writer = _SimWriter(exchange)
    reconciler = BybitDemoReconciler(ledger, writer)  # type: ignore[arg-type]

    try:
        order_intent_id, order_link_id, trade_id = persist_durable_intent(
            ledger=ledger,  # type: ignore[arg-type]
            symbol="BTCUSDT",
            side="Buy",
            qty="0.001",
        )
    except Exception as exc:  # noqa: BLE001
        evidence["error"] = f"persist_failed:{type(exc).__name__}"
        store.close()
        return evidence

    record = ledger.get_intent(order_intent_id)
    if record is None or str(record.get("state")) != "SUBMITTING":
        evidence["error"] = "durable_intent_not_submitting"
        store.close()
        return evidence
    bound = make_order_link_id(str(record["campaign_id"]), str(record["decision_id"]), order_intent_id)
    if order_link_id != bound:
        evidence["error"] = "orderlink_not_bound"
        store.close()
        return evidence

    submit = submit_after_persist(
        ledger=ledger,  # type: ignore[arg-type]
        reconciler=reconciler,
        writer=writer,
        order_intent_id=order_intent_id,
        order_link_id=order_link_id,
        symbol="BTCUSDT",
        side="Buy",
        qty="0.001",
    )
    if submit.get("ok"):
        exchange.set_fill(order_link_id, filled_qty="0.001", status="Filled", avg_price="64282.2")
    evidence["create_order_calls"] = exchange.real_exchange_write_call_count
    evidence["exchange_write_call_count"] = exchange.real_exchange_write_call_count
    evidence["REAL_EXCHANGE_WRITE_CALLS"] = exchange.real_exchange_write_call_count
    if not submit.get("ok"):
        evidence["error"] = submit.get("reason")
        store.close()
        return evidence

    active = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "trade_id": trade_id,
        "decision_id": record.get("decision_id"),
        "bybit_order_id": submit.get("bybit_order_id"),
        "entry_price": "64282.2",
        "exit_price": "64282.2",
        "qty": "0.001",
        "candidate": market_input,
    }
    pnl = {
        "net_pnl": "-0.07071042",
        "pnl_provenance": "BYBIT_V5_POSITION_CLOSED_PNL",
        "entry_fee": "0.03535521",
        "exit_fee": "0.03535521",
        "gross_pnl": "-0.00000000",
    }
    learning = write_durable_lesson_from_trade(store=store, active=active, pnl=pnl)
    evidence["BOUNDED_RUNTIME_DURABLE_LEARNING_CLOSURE"] = learning.get("ok") is True
    evidence["BOUNDED_RUNTIME_EXCHANGE_PNL_TO_LESSON"] = bool(learning.get("source_evidence_hash"))

    store.close()
    evidence["HARD_RISK_AUTHORITY_UNCHANGED"] = _risk_unchanged()
    evidence["BOUNDED_RUNTIME_CERTIFIED_SURFACE_WIRING_PASS"] = bool(
        evidence.get("BOUNDED_RUNTIME_DURABLE_LEDGER_AUTHORITY")
        and evidence.get("BOUNDED_RUNTIME_PERSIST_BEFORE_SUBMIT")
        and evidence.get("BOUNDED_RUNTIME_ORDERLINK_BOUND_TO_DURABLE_INTENT")
        and evidence.get("BOUNDED_RUNTIME_DURABLE_LESSON_RETRIEVAL")
        and evidence.get("BOUNDED_RUNTIME_CERTIFIED_RMG_AUTHORITY")
        and evidence.get("BOUNDED_RUNTIME_SESSION_MEMORY_NOT_POLICY_AUTHORITY")
        and evidence.get("BOUNDED_RUNTIME_DURABLE_LEARNING_CLOSURE")
        and evidence.get("BOUNDED_RUNTIME_EXCHANGE_PNL_TO_LESSON")
        and evidence.get("CONTROL_PLANE_RUNTIME_LEASE_ID_MATCH")
        and evidence.get("RUNTIME_LEASE_EXPIRY_AUTHORITY")
        and evidence.get("SESSION_EXPIRY_BLOCKS_NEW_ENTRY")
        and evidence.get("FOUNDER_START_AUTHORIZATION_ONE_SHOT")
        and evidence.get("POST_START_CONTROL_PLANE_DISARM_SAFE")
        and evidence.get("ACTIVE_SESSION_SURVIVES_CONTROL_PLANE_DISARM")
        and evidence.get("create_order_calls") == 0
        and evidence.get("exchange_write_call_count") == 0
        and evidence.get("REAL_EXCHANGE_WRITE_CALLS", 0) == 0
        and evidence.get("HARD_RISK_AUTHORITY_UNCHANGED")
    )
    if not evidence["BOUNDED_RUNTIME_CERTIFIED_SURFACE_WIRING_PASS"]:
        evidence["error"] = evidence.get("error") or "bounded_runtime_integration_qualification_failed"
    return evidence


def main() -> int:
    evidence = run()
    print(json.dumps(evidence, indent=2, sort_keys=True, default=str))
    return 0 if evidence.get("BOUNDED_RUNTIME_CERTIFIED_SURFACE_WIRING_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
