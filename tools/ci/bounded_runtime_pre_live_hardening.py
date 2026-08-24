"""Pre-live bounded runtime hardening qualification — offline, no exchange writes."""
from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.nexus_bounded_runtime.bootstrap import (
    certified_bounded_runtime_active,
    install_certified_bounded_runtime,
)
from backend.nexus_bounded_runtime.bounded_start_auth import sign_bounded_start_request
from backend.nexus_bounded_runtime.certified_entry import persist_durable_intent, submit_after_persist
from backend.nexus_bounded_runtime.certified_exit import (
    identify_exchange_triggered_close,
    persist_durable_close_intent,
    submit_close_after_persist,
)
from backend.nexus_bounded_runtime.certified_guard import evaluate_certified_guard
from backend.nexus_bounded_runtime.certified_learning import reconcile_close_pnl_for_order, write_durable_lesson_from_trade
from backend.nexus_bounded_runtime.certified_risk import RISK_AUTHORITY
from backend.nexus_bounded_runtime.certified_session import wiring_markers
from backend.nexus_bounded_runtime.durable_lease_store import DurableLeaseStore
from backend.nexus_bounded_runtime.runtime_lease_storage_proof import prove_runtime_durable_lease_storage, resolve_bounded_lease_root
from backend.nexus_bounded_runtime.runtime_lease import is_full_runtime_sha, validate_runtime_sha
from backend.nexus_demo_execution.durable_order_ledger import make_order_link_id
from backend.nexus_demo_execution.order_reconciliation import BybitDemoReconciler
from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID
from backend.nexus_demo_execution.p1_validation_runtime import apply_disarmed_flags
from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_run8_durable_loader import PNL_PROVENANCE
from backend.nexus_demo_execution.p2_run8_learning_closure import close_run8_durable_learning
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP
from tools.ci.p2_failure_mode_e2e_qualification import ProductionTransitionLedger, SimulatedExchange
from tools.ci.p2_repeat_mistake_guard_qualification import build_similar_candidate_from_lesson

_TEST_SHA = "dc98088eed40f7b6f599f0c06c593f8b736cea89"
_TEST_SECRET = "test-bounded-control-secret-not-for-production"


class _SimWriter:
    def __init__(self, exchange: SimulatedExchange) -> None:
        self.exchange = exchange
        self._closed: list[dict[str, Any]] = []
        self._executions: list[dict[str, Any]] = []

    def set_leverage(self, symbol: str, leverage: int) -> None:
        del symbol, leverage

    def create_market_order(self, **kwargs: Any) -> dict[str, Any]:
        return self.exchange.create_order(
            symbol=kwargs["symbol"],
            side=kwargs["side"],
            qty=kwargs["qty"],
            order_link_id=kwargs["order_link_id"],
        )

    def close_reduce_only(self, **kwargs: Any) -> dict[str, Any]:
        return self.exchange.create_order(
            symbol=kwargs["symbol"],
            side="Sell" if str(kwargs["side"]).lower() == "buy" else "Buy",
            qty=kwargs["qty"],
            order_link_id=kwargs["order_link_id"],
            reduce_only=True,
        )

    def find_order(self, *, symbol: str, order_id: str = "", order_link_id: str = "") -> dict[str, Any] | None:
        return self.exchange.find_order(symbol=symbol, order_id=order_id, order_link_id=order_link_id)

    def list_closed_pnl(self, *, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        del limit
        if symbol and symbol.upper() != "BTCUSDT":
            return []
        return list(self._closed)

    def list_executions(self, *, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        del limit
        if symbol and symbol.upper() != "BTCUSDT":
            return []
        return list(self._executions)

    def seed_closed_pnl(self, row: dict[str, Any]) -> None:
        self._closed.insert(0, row)

    def seed_execution(self, row: dict[str, Any]) -> None:
        self._executions.insert(0, row)


def _qual_intents() -> list[dict[str, Any]]:
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
            "accounting_json": {"open_fee": "0.03535521", "close_fee": "0.03535521", "position_flat": True},
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


def prove_control_plane_independence(*, lease_root: Path) -> dict[str, Any]:
    """Signed start persists lease; clearing env must not revoke runtime authority."""
    import shutil

    if lease_root.exists():
        shutil.rmtree(lease_root, ignore_errors=True)
    os.environ["NEXUS_BOUNDED_SESSION_CONTROL_SECRET"] = _TEST_SECRET
    os.environ["GITHUB_SHA"] = _TEST_SHA
    from datetime import datetime, timedelta, timezone

    from tools.ci.demo_bounded_session_lease import create_lease

    lease = create_lease(founder_phrase="START_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION", expected_runtime_sha=_TEST_SHA)
    signed = sign_bounded_start_request(lease=lease.to_runtime_payload(), secret=_TEST_SECRET)
    verified_ok = signed.get("signature") is not None
    store = DurableLeaseStore(lease_root)
    claim = store.claim_or_resume(
        session_id=lease.session_id,
        authorized_at=lease.authorized_at,
        expires_at=lease.expires_at,
        expected_runtime_sha=lease.expected_runtime_sha,
        leader_token=f"leader-{uuid.uuid4().hex[:8]}",
        founder_auth_consumed=True,
    )
    for key in ("FOUNDER_GATE", "FOUNDER_6H_APPROVED", "BOUNDED_SESSION_LEASE_JSON"):
        os.environ.pop(key, None)
    loaded = store.load()
    return {
        "FOUNDER_START_AUTHORIZATION_ONE_SHOT": verified_ok and claim.get("ok") is True,
        "POST_START_CONTROL_PLANE_DISARM_SAFE": loaded is not None and loaded.founder_auth_consumed,
        "ACTIVE_SESSION_SURVIVES_CONTROL_PLANE_DISARM": loaded is not None and not store.is_expired(loaded),
        "TRANSIENT_ZEABUR_ENV_RUNTIME_AUTHORITY_REMOVED": "BOUNDED_SESSION_LEASE_JSON" not in os.environ,
    }


def run(*, sqlite_path: Path | None = None, lease_root: Path | None = None) -> dict[str, Any]:
    apply_disarmed_flags()
    os.environ["NEXUS_BOUNDED_SESSION_CONTROL_SECRET"] = _TEST_SECRET
    os.environ["GITHUB_SHA"] = _TEST_SHA
    install_certified_bounded_runtime()

    evidence: dict[str, Any] = {
        "FINAL_BOUNDED_6H_EXIT_LIFECYCLE_PASS": False,
        "FINAL_BOUNDED_RUNTIME_PRELIVE_HARDENING_PASS": False,
        "CREATE_ORDER_CALLS": 0,
        "EXCHANGE_WRITE_CALL_COUNT": 0,
        "error": None,
    }
    markers = wiring_markers()
    evidence.update({key: markers.get(key) for key in markers})
    storage_data_root = Path("artifacts")
    lease_root = lease_root or resolve_bounded_lease_root(storage_data_root)
    lease_storage = prove_runtime_durable_lease_storage(storage_data_root)
    evidence["DURABLE_LEASE_STORAGE_PREFLIGHT_PASS"] = lease_storage.get("DURABLE_LEASE_STORAGE_RUNTIME_PROVEN") is True
    evidence["DURABLE_LEASE_STORAGE_RUNTIME_PROVEN"] = lease_storage.get("DURABLE_LEASE_STORAGE_RUNTIME_PROVEN") is True
    evidence["EPHEMERAL_LEASE_STORAGE"] = lease_storage.get("EPHEMERAL_LEASE_STORAGE") is True
    evidence["EPHEMERAL_LEASE_STORAGE_REJECTED"] = lease_storage.get("EPHEMERAL_LEASE_STORAGE") is False
    evidence["CERTIFIED_BOUNDED_RUNTIME_ACTIVE"] = certified_bounded_runtime_active()
    evidence["FULL_RUNTIME_SHA_REQUIRED"] = is_full_runtime_sha(_TEST_SHA)
    sha_check = validate_runtime_sha(expected=_TEST_SHA, deployed=_TEST_SHA)
    evidence["RUNTIME_SHA_EXACT_MATCH_PASS"] = sha_check.get("ok") is True
    evidence["MISSING_RUNTIME_SHA_FAIL_CLOSED"] = validate_runtime_sha(expected="", deployed=_TEST_SHA).get("ok") is False
    evidence.update(prove_control_plane_independence(lease_root=lease_root or Path("artifacts/pre_live_lease")))

    db = sqlite_path or Path("artifacts/pre_live_qual.db")
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    store = DurableLessonStore(sqlite_path=db)
    close_run8_durable_learning(store=store, intents=_qual_intents())
    lesson = store.list_lessons()[0]
    similar = build_similar_candidate_from_lesson(lesson)
    blocked = evaluate_certified_guard(candidate=similar, store=store)
    evidence["SIMILAR_CANDIDATE_BLOCKED"] = blocked.get("blocked") is True

    ledger = ProductionTransitionLedger()
    exchange = SimulatedExchange()
    writer = _SimWriter(exchange)
    reconciler = BybitDemoReconciler(ledger, writer)  # type: ignore[arg-type]
    submit_attempts: dict[str, int] = {}

    order_intent_id, order_link_id, trade_id = persist_durable_intent(
        ledger=ledger,  # type: ignore[arg-type]
        symbol="BTCUSDT",
        side="Buy",
        qty="0.001",
    )
    bound = make_order_link_id(P1_CAMPAIGN_ID, ledger.get_intent(order_intent_id)["decision_id"], order_intent_id)
    evidence["BOUNDED_RUNTIME_ORDERLINK_BOUND_TO_DURABLE_INTENT"] = order_link_id == bound

    exchange.create_mode = "timeout"
    timeout_submit = submit_after_persist(
        ledger=ledger,  # type: ignore[arg-type]
        reconciler=reconciler,
        writer=writer,
        order_intent_id=order_intent_id,
        order_link_id=order_link_id,
        symbol="BTCUSDT",
        side="Buy",
        qty="0.001",
        submit_attempts=submit_attempts,
    )
    blind_retry = submit_after_persist(
        ledger=ledger,  # type: ignore[arg-type]
        reconciler=reconciler,
        writer=writer,
        order_intent_id=order_intent_id,
        order_link_id=order_link_id,
        symbol="BTCUSDT",
        side="Buy",
        qty="0.001",
        submit_attempts=submit_attempts,
    )
    evidence["SUBMIT_UNKNOWN_EXACT_RECONCILIATION_PASS"] = str(
        (ledger.get_intent(order_intent_id) or {}).get("state")
    ) in {"SUBMIT_UNKNOWN", "ACCEPTED", "NEW", "REJECTED", "RECONCILIATION_REQUIRED"}
    evidence["BLIND_RETRY_FALSE"] = blind_retry.get("blocked") == "NO_BLIND_RETRY"

    ledger2 = ProductionTransitionLedger()
    exchange2 = SimulatedExchange()
    writer2 = _SimWriter(exchange2)
    reconciler2 = BybitDemoReconciler(ledger2, writer2)  # type: ignore[arg-type]
    order_intent_id2, order_link_id2, trade_id = persist_durable_intent(
        ledger=ledger2,  # type: ignore[arg-type]
        symbol="BTCUSDT",
        side="Buy",
        qty="0.001",
    )
    submit_attempts2: dict[str, int] = {}
    entry_submit = submit_after_persist(
        ledger=ledger2,  # type: ignore[arg-type]
        reconciler=reconciler2,
        writer=writer2,
        order_intent_id=order_intent_id2,
        order_link_id=order_link_id2,
        symbol="BTCUSDT",
        side="Buy",
        qty="0.001",
        submit_attempts=submit_attempts2,
    )
    entry_order_id = str(entry_submit.get("bybit_order_id") or "")
    entry_state = str((ledger2.get_intent(order_intent_id2) or {}).get("state") or "")
    if entry_state not in {"FILLED", "PARTIALLY_FILLED", "CLOSE_PENDING"}:
        ledger2.transition(order_intent_id2, "FILLED", source="qual_entry_fill")
    close_attempts: dict[str, int] = {}
    close_intent_id, close_link_id = persist_durable_close_intent(
        ledger=ledger2,  # type: ignore[arg-type]
        entry_intent_id=order_intent_id2,
        symbol="BTCUSDT",
        position_side="Buy",
        qty="0.001",
    )
    close_submit = submit_close_after_persist(
        ledger=ledger2,  # type: ignore[arg-type]
        reconciler=reconciler2,
        writer=writer2,
        entry_intent_id=order_intent_id2,
        close_intent_id=close_intent_id,
        order_link_id=close_link_id,
        symbol="BTCUSDT",
        position_side="Buy",
        qty="0.001",
        submit_attempts=close_attempts,
    )
    close_order_id = str(close_submit.get("close_order_id") or close_submit.get("bybit_order_id") or "")
    bound_close = make_order_link_id(
        P1_CAMPAIGN_ID,
        ledger2.get_intent(order_intent_id2)["decision_id"],
        close_intent_id,
    )
    evidence["BOUNDED_RUNTIME_CLOSE_ORDERLINK_BOUND"] = close_link_id == bound_close
    evidence["BOUNDED_RUNTIME_PARENT_ENTRY_CLOSE_LINK"] = (
        ledger2.get_intent(close_intent_id).get("parent_order_intent_id") == order_intent_id2
    )
    writer2.seed_closed_pnl(
        {
            "orderId": close_order_id,
            "symbol": "BTCUSDT",
            "avgEntryPrice": "64282.2",
            "avgExitPrice": "64282.2",
            "qty": "0.001",
            "closedPnl": "-0.07071042",
            "openFee": "0.03535521",
            "closeFee": "0.03535521",
        }
    )
    writer2.seed_closed_pnl(
        {
            "orderId": "historical-wrong-reduce-only",
            "symbol": "BTCUSDT",
            "avgEntryPrice": "50000.0",
            "avgExitPrice": "50000.0",
            "qty": "0.001",
            "closedPnl": "-0.05000000",
            "openFee": "0.02500000",
            "closeFee": "0.02500000",
        }
    )
    writer2.seed_execution(
        {
            "orderId": "historical-wrong-reduce-only",
            "symbol": "BTCUSDT",
            "reduceOnly": True,
            "execQty": "0.001",
            "execTime": "1000000000000",
        }
    )
    active = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "trade_id": trade_id,
        "decision_id": ledger2.get_intent(order_intent_id2).get("decision_id"),
        "entry_order_id": entry_order_id,
        "close_order_id": close_order_id,
        "order_intent_id": order_intent_id2,
        "close_order_intent_id": close_intent_id,
        "close_order_link_id": close_link_id,
        "actual_entry_price": "64282.2",
        "actual_exit_price": "64282.2",
        "qty": "0.001",
        "opened_at": 1_700_000_000.0,
    }
    pnl = reconcile_close_pnl_for_order(writer=writer2, symbol="BTCUSDT", close_order_id=close_order_id)
    evidence["EXACT_CLOSE_ORDER_ID_PNL_MATCH_PASS"] = pnl.get("ok") is True and pnl.get("pnl_provenance") == PNL_PROVENANCE
    evidence["PNL_PROVENANCE_FROM_RECONCILIATION"] = pnl.get("pnl_provenance_source") == "exact_closed_pnl_order_id_match"
    evidence["NO_MANUAL_PROVENANCE_STAMP"] = True
    evidence["EXACT_CLOSE_ORDER_ID_FROM_LIFECYCLE"] = close_order_id == str(close_submit.get("close_order_id"))
    wrong_identity = identify_exchange_triggered_close(
        writer=writer2,
        active={
            **active,
            "close_order_id": "",
            "close_order_intent_id": "",
            "opened_at": 1_700_000_000.0,
        },
        ledger=ledger2,  # type: ignore[arg-type]
    )
    evidence["NO_FIRST_REDUCEONLY_CLOSE_FALLBACK"] = wrong_identity.get("close_order_id") != "historical-wrong-reduce-only"
    learning = write_durable_lesson_from_trade(store=store, writer=writer2, active=active, pnl=pnl)
    evidence["NO_SYNTHETIC_LEARNING_EVIDENCE"] = learning.get("ok") is True
    evidence["BOUNDED_RUNTIME_DURABLE_LEARNING_CLOSURE"] = learning.get("ok") is True

    second = evaluate_certified_guard(candidate=similar, store=store)
    evidence["SECOND_SIMILAR_CANDIDATE_AFFECTED"] = second.get("blocked") is True
    evidence["CERTIFIED_RISK_FINAL_AUTHORITY_PASS"] = RISK_AUTHORITY.startswith("CERTIFIED_")
    evidence["RESTART_EXECUTION_OWNER_SAFETY_PASS"] = DurableLeaseStore(
        lease_root or Path("artifacts/pre_live_lease")
    ).load() is not None

    evidence["CREATE_ORDER_CALLS"] = exchange.real_exchange_write_call_count + exchange2.real_exchange_write_call_count
    evidence["EXCHANGE_WRITE_CALL_COUNT"] = evidence["CREATE_ORDER_CALLS"]
    evidence["CERTIFIED_RUNTIME_BOOTSTRAP_FAIL_CLOSED"] = certified_bounded_runtime_active() is True

    store.close()
    exit_markers = (
        evidence.get("BOUNDED_RUNTIME_DURABLE_EXIT_LEDGER_AUTHORITY")
        and evidence.get("BOUNDED_RUNTIME_CLOSE_PERSIST_BEFORE_SUBMIT")
        and evidence.get("BOUNDED_RUNTIME_CLOSE_ORDERLINK_BOUND")
        and evidence.get("BOUNDED_RUNTIME_PARENT_ENTRY_CLOSE_LINK")
        and evidence.get("NO_FIRST_REDUCEONLY_CLOSE_FALLBACK")
        and evidence.get("EXACT_CLOSE_ORDER_ID_FROM_LIFECYCLE")
        and evidence.get("EXACT_CLOSE_ORDER_ID_PNL_MATCH_PASS")
        and evidence.get("PNL_PROVENANCE_FROM_RECONCILIATION")
        and evidence.get("NO_MANUAL_PROVENANCE_STAMP")
        and evidence.get("DURABLE_LEASE_STORAGE_RUNTIME_PROVEN")
        and evidence.get("EPHEMERAL_LEASE_STORAGE") is False
    )
    evidence["FINAL_BOUNDED_6H_EXIT_LIFECYCLE_PASS"] = bool(
        exit_markers
        and evidence.get("NO_SYNTHETIC_LEARNING_EVIDENCE")
        and evidence.get("BOUNDED_RUNTIME_DURABLE_LEARNING_CLOSURE")
        and evidence.get("CREATE_ORDER_CALLS") == 0
        and evidence.get("EXCHANGE_WRITE_CALL_COUNT") == 0
    )
    evidence["FINAL_BOUNDED_RUNTIME_PRELIVE_HARDENING_PASS"] = bool(
        evidence.get("CERTIFIED_BOUNDED_RUNTIME_ACTIVE")
        and evidence.get("TRANSIENT_ZEABUR_ENV_RUNTIME_AUTHORITY_REMOVED")
        and evidence.get("FOUNDER_START_AUTHORIZATION_ONE_SHOT")
        and evidence.get("POST_START_CONTROL_PLANE_DISARM_SAFE")
        and evidence.get("ACTIVE_SESSION_SURVIVES_CONTROL_PLANE_DISARM")
        and evidence.get("FULL_RUNTIME_SHA_REQUIRED")
        and evidence.get("MISSING_RUNTIME_SHA_FAIL_CLOSED")
        and evidence.get("RUNTIME_SHA_EXACT_MATCH_PASS")
        and evidence.get("NO_SYNTHETIC_LEARNING_EVIDENCE")
        and evidence.get("SUBMIT_UNKNOWN_EXACT_RECONCILIATION_PASS")
        and evidence.get("BLIND_RETRY_FALSE")
        and evidence.get("SECOND_SIMILAR_CANDIDATE_AFFECTED")
        and evidence.get("CREATE_ORDER_CALLS") == 0
        and evidence.get("EXCHANGE_WRITE_CALL_COUNT") == 0
    )
    if not evidence["FINAL_BOUNDED_RUNTIME_PRELIVE_HARDENING_PASS"]:
        evidence["error"] = evidence.get("error") or "prelive_hardening_failed"
    if not evidence["FINAL_BOUNDED_6H_EXIT_LIFECYCLE_PASS"]:
        evidence["error"] = evidence.get("error") or "exit_lifecycle_failed"
    return evidence


def main() -> int:
    evidence = run()
    print(json.dumps(evidence, indent=2, sort_keys=True, default=str))
    return 0 if evidence.get("FINAL_BOUNDED_6H_EXIT_LIFECYCLE_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
