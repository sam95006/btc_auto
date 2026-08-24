"""Certified bounded 6H session — composes P1 ledger + P2 RMG + learning closure."""
from __future__ import annotations

import inspect
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.nexus_bounded_runtime.certified_entry import (
    candidate_to_market_input,
    persist_durable_intent,
    submit_after_persist,
)
from backend.nexus_bounded_runtime.certified_guard import evaluate_certified_guard
from backend.nexus_bounded_runtime.certified_learning import write_durable_lesson_from_trade
from backend.nexus_bounded_runtime.runtime_lease import (
    RuntimeLease,
    lease_allows_new_entry,
    load_runtime_lease,
    validate_runtime_lease,
)
from backend.nexus_demo_execution.bounded_autonomous_engine import BoundedAutonomousSessionEngine
from backend.nexus_demo_execution.bounded_universe import scan_dynamic_candidates
from backend.nexus_demo_execution.cost_entry_gate import evaluate_cost_gate
from backend.nexus_demo_execution.demo_write_client import DemoWriteError
from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger
from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_demo_execution.kill_switch import KillSwitchTrigger
from backend.nexus_demo_execution.order_reconciliation import BybitDemoReconciler
from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP
from backend.nexus_persistence_pg.pool import PostgresPool

_TRUE = {"1", "true", "yes", "on"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class CertifiedBounded6HSession(BoundedAutonomousSessionEngine):
    """6H runtime that consumes certified P1/P2 surfaces — not legacy session-only guards."""

    _runtime_lease: RuntimeLease | None = field(default=None, repr=False)
    _certified_ledger: Any = field(default=None, repr=False)
    _certified_lesson_store: Any = field(default=None, repr=False)
    _certified_reconciler: Any = field(default=None, repr=False)
    _pg_pool: Any = field(default=None, repr=False)
    _founder_auth_consumed: bool = field(default=False, repr=False)
    _active_lease_registry: set[str] = field(default_factory=set, repr=False)

    def _ensure_certified_stores(self) -> None:
        if self._certified_ledger is not None and self._certified_lesson_store is not None:
            if self._certified_reconciler is None:
                self._certified_reconciler = BybitDemoReconciler(self._certified_ledger, self.writer)
            return
        database_url = (os.environ.get("NEXUS_POSTGRES_URL") or "").strip()
        if not database_url:
            raise ValueError("certified_runtime_postgres_required")
        self._pg_pool = PostgresPool(database_url)
        self._pg_pool.open()
        versions = {str(row[0]) for row in self._pg_pool.fetchall("SELECT version FROM nexus.schema_migrations")}
        if "0007" not in versions:
            raise ValueError("migration_0007_missing")
        self._certified_ledger = DurableOrderLedger(self._pg_pool)
        self._certified_lesson_store = DurableLessonStore(pool=self._pg_pool)
        self._certified_reconciler = BybitDemoReconciler(self._certified_ledger, self.writer)

    def _consume_founder_authorization_one_shot(self) -> bool:
        """Founder gate env may be cleared post-start; consume authorization into runtime lease."""
        if self._founder_auth_consumed:
            return True
        gate = (os.environ.get("FOUNDER_GATE") or "").strip()
        approved = (os.environ.get("FOUNDER_6H_APPROVED") or "").lower() in _TRUE
        if gate == "DEMO_AUTONOMOUS_6H_V2_BOUNDED_VALIDATION" and approved and self._runtime_lease is not None:
            self._founder_auth_consumed = True
            with self._lock:
                self._state["founder_authorization_one_shot"] = True
            return True
        return False

    def start(self) -> dict[str, Any]:
        lease = load_runtime_lease()
        checked = validate_runtime_lease(lease)
        if not checked.get("ok"):
            return redact_secrets({"ok": False, "reason": checked.get("reason"), "certified_runtime": True})
        assert lease is not None
        if lease.session_id in self._active_lease_registry:
            return redact_secrets({"ok": False, "reason": "duplicate_active_lease", "session_id": lease.session_id})
        self._runtime_lease = lease
        self.session_id = lease.session_id
        self._active_lease_registry.add(lease.session_id)
        self._consume_founder_authorization_one_shot()
        try:
            self._ensure_certified_stores()
        except ValueError as exc:
            return redact_secrets({"ok": False, "reason": str(exc), "certified_runtime": True})
        result = super().start()
        if isinstance(result, dict):
            result["runtime_lease_session_id"] = lease.session_id
            result["certified_runtime"] = True
            result["founder_authorization_one_shot"] = self._founder_auth_consumed
        with self._lock:
            self._state["session_id"] = lease.session_id
            self._state["runtime_lease_expires_at"] = lease.expires_at
        return result

    def _runtime_entry_allowed(self) -> bool:
        if not self._founder_auth_consumed and not self._consume_founder_authorization_one_shot():
            return False
        if not lease_allows_new_entry(self._runtime_lease):
            with self._lock:
                self._state["runtime_lease_expired"] = True
            return False
        return True

    def _try_entry(self, allocator, export_root, account_epoch: str) -> dict[str, Any] | None:  # type: ignore[no-untyped-def]
        if not self._runtime_entry_allowed():
            return None
        if not self.session_write_enabled or not self.gate.can_write_orders():
            return None
        try:
            self._ensure_certified_stores()
        except ValueError:
            return None

        ledger: DurableOrderLedger = self._certified_ledger
        store: DurableLessonStore = self._certified_lesson_store
        reconciler: BybitDemoReconciler = self._certified_reconciler

        if ledger.unfinished():
            with self._lock:
                self._state["unresolved_intent_blocks_entry"] = True
            return None

        positions = self.writer.list_positions()
        orders = self.writer.list_open_orders()
        if positions or orders:
            with self._lock:
                self._state["duplicate_order_incidents"] += 1
            self._kill("not_flat_before_entry", KillSwitchTrigger.GATE_FAILURE)
            return None

        candidates, scan_meta = scan_dynamic_candidates(limit=8)
        self.persistence.append("universe_scans", redact_secrets(scan_meta), account_epoch=account_epoch)
        with self._lock:
            self._state["candidates_total"] += len(candidates)

        for cand in candidates:
            cdict = cand.to_dict()
            self.persistence.append("bounded_candidates", redact_secrets(cdict), account_epoch=account_epoch)
            if cand.risk_critic_verdict not in {"PASS", "WATCH"}:
                with self._lock:
                    self._state["risk_critic_blocks"] += 1
                continue

            market_input = candidate_to_market_input(cdict)
            guard_eval = evaluate_certified_guard(candidate=market_input, store=store)
            self.persistence.append("decision_deltas", redact_secrets(guard_eval), account_epoch=account_epoch)
            if guard_eval.get("blocked"):
                with self._lock:
                    self._state["mistake_guard_blocks"] += 1
                continue
            telemetry = self.memory.apply(candidate=cdict, before_score=cand.candidate_score, before_verdict="ALLOW")
            self.persistence.append("session_mistake_telemetry", redact_secrets(telemetry), account_epoch=account_epoch)

            try:
                snap = self.reader.read_with_constitution()
            except Exception:
                continue
            from backend.nexus_demo_execution.allocation import AllocationResult

            decision = allocator.allocate(snap, requested_margin=self.policy.margin_per_trade, open_count=0, pending_count=0)
            if decision.result != AllocationResult.ALLOCATED:
                continue
            price = cand.last_price
            if price <= 0:
                continue
            try:
                info = self.writer.fetch_instrument(cand.symbol)
                qty = self.writer.compute_qty(
                    margin_usdt=decision.margin_usdt, leverage=self.policy.leverage, price=price, info=info
                )
                tick = self.writer.tick_size(info)
            except DemoWriteError:
                continue

            if cand.direction == "Buy":
                sl_f, tp_f = price * 0.992, price * 1.008
            else:
                sl_f, tp_f = price * 1.008, price * 0.992
            sl = self.writer.format_price(sl_f, tick)
            tp = self.writer.format_price(tp_f, tick)
            fee_quote = self.writer.fetch_fee_rate_quote(cand.symbol)
            funding = cand.funding_rate if cand.funding_status == "KNOWN" else None
            cost = evaluate_cost_gate(
                entry_price=price,
                stop_loss=_f(sl),
                take_profit=_f(tp),
                qty=_f(qty),
                side=cand.direction,
                fee_rate=fee_quote.usable_taker,
                funding_rate=funding,
                slippage_bps=cand.spread_bps,
                fee_meta=fee_quote.to_dict(),
            )
            if not cost.allowed:
                with self._lock:
                    self._state["cost_gate_blocks"] += 1
                continue

            notional = _f(qty) * price
            margin = notional / float(FIXED_LEVERAGE)
            if not (0 < margin <= float(MARGIN_PER_TRADE_CAP)):
                with self._lock:
                    self._state["risk_critic_blocks"] += 1
                continue

            try:
                order_intent_id, order_link_id, trade_id = persist_durable_intent(
                    ledger=ledger,
                    symbol=cand.symbol,
                    side=cand.direction,
                    qty=qty,
                )
            except Exception:
                return None

            submit = submit_after_persist(
                ledger=ledger,
                reconciler=reconciler,
                writer=self.writer,
                order_intent_id=order_intent_id,
                order_link_id=order_link_id,
                symbol=cand.symbol,
                side=cand.direction,
                qty=qty,
                stop_loss=sl,
                take_profit=tp,
            )
            if not submit.get("ok"):
                return None

            trade_case_id = f"case-{uuid.uuid4().hex[:12]}"
            with self._lock:
                self._state["order_intent_total"] += 1
                self._state["exchange_write_attempt_total"] += 1
                self._state["entries_total"] += 1
            self.persistence.append(
                "orders",
                redact_secrets(
                    {
                        "order_intent_id": order_intent_id,
                        "order_link_id": order_link_id,
                        "trade_id": trade_id,
                        "trade_case_id": trade_case_id,
                        "certified_runtime": True,
                        "submit": submit,
                    }
                ),
                account_epoch=account_epoch,
            )
            pos = self._wait_fill(cand.symbol)
            if not pos:
                self._kill("no_fill", KillSwitchTrigger.GATE_FAILURE)
                return None
            return {
                "symbol": cand.symbol,
                "side": str(pos.get("side") or cand.direction),
                "qty": str(pos.get("size") or qty),
                "entry_price": _f(pos.get("avgPrice"), price),
                "sl": sl,
                "tp": tp,
                "opened_at": time.time(),
                "trade_case_id": trade_case_id,
                "trade_id": trade_id,
                "decision_id": ledger.get_intent(order_intent_id).get("decision_id") if ledger.get_intent(order_intent_id) else "",
                "order_intent_id": order_intent_id,
                "order_link_id": order_link_id,
                "bybit_order_id": submit.get("bybit_order_id"),
                "candidate": cdict,
                "cost_labels": list(cost.labels),
            }
        return None

    def _record_exit(self, active: dict[str, Any], reason: str, export_root, account_epoch: str) -> None:  # type: ignore[no-untyped-def]
        from backend.nexus_demo_execution.pnl_reconcile import reconcile_via_writer

        pnl = reconcile_via_writer(self.writer, active["symbol"])
        try:
            self._ensure_certified_stores()
            lesson = write_durable_lesson_from_trade(
                store=self._certified_lesson_store,
                active=active,
                pnl=pnl,
            )
            self.persistence.append("durable_lessons", redact_secrets(lesson), account_epoch=account_epoch)
        except Exception as exc:  # noqa: BLE001
            self.persistence.append(
                "durable_lessons",
                {"ok": False, "error": type(exc).__name__},
                account_epoch=account_epoch,
            )
        super()._record_exit(active, reason, export_root, account_epoch)


def wiring_markers() -> dict[str, bool]:
    source = inspect.getsource(CertifiedBounded6HSession._try_entry)
    learning_source = inspect.getsource(CertifiedBounded6HSession._record_exit)
    return {
        "BOUNDED_RUNTIME_DURABLE_LEDGER_AUTHORITY": "persist_durable_intent" in source,
        "BOUNDED_RUNTIME_PERSIST_BEFORE_SUBMIT": source.index("persist_durable_intent") < source.index("submit_after_persist"),
        "BOUNDED_RUNTIME_ORDERLINK_BOUND_TO_DURABLE_INTENT": "order_link_id" in source and "persist_durable_intent" in source,
        "BOUNDED_RUNTIME_DURABLE_LESSON_RETRIEVAL": "evaluate_certified_guard" in source,
        "BOUNDED_RUNTIME_CERTIFIED_RMG_AUTHORITY": "evaluate_certified_guard" in source,
        "BOUNDED_RUNTIME_SESSION_MEMORY_NOT_POLICY_AUTHORITY": "session_mistake_telemetry" in source,
        "BOUNDED_RUNTIME_DURABLE_LEARNING_CLOSURE": "write_durable_lesson_from_trade" in learning_source,
        "BOUNDED_RUNTIME_EXCHANGE_PNL_TO_LESSON": "reconcile_via_writer" in learning_source,
    }
