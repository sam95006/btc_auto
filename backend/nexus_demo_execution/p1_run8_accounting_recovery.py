"""Founder-dispatch Run #8 post-trade accounting recovery.

Exchange phase is read-only. Ledger finalization writes PostgreSQL only.
Never creates, closes, or cancels an exchange order.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient
from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger
from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_demo_execution.p1_exchange_accounting import (
    ClosedAtError,
    aggregate_executions,
    bounded_window_ms,
    closed_at_from_closed_pnl_row,
    is_exchange_backed_provenance,
    is_provisional_provenance,
    list_executions_for_order,
    match_closed_pnl_by_close_order_id,
    poll_exact_closed_pnl,
    realized_pnl_absent,
)
from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID, sanitize_evidence
from backend.nexus_demo_execution.p1_validation_runtime import (
    apply_disarmed_flags,
    exception_type_name,
    write_json_file,
)
from backend.nexus_demo_execution.runtime_identity import (
    read_container_baked_commit,
    read_container_source_commit,
)


CONFIRM_PHRASE = "RECOVER_BYBIT_DEMO_P1_RUN8_ACCOUNTING"
PNL_PROVENANCE = "BYBIT_V5_POSITION_CLOSED_PNL"
IDENTITY_PREFIX_LEN = 12
POLL_INTERVAL_SEC = 2.0
POLL_TIMEOUT_SEC = 60.0
WRITE_METHODS = frozenset(
    {
        "create_market_order",
        "close_reduce_only",
        "cancel_order",
        "create_order",
        "_post",
    }
)
SECRET_ENV_KEYS = (
    "BYBIT_DEMO_API_KEY",
    "BYBIT_DEMO_API_SECRET",
    "NEXUS_STAGING_POSTGRES_URL",
    "NEXUS_POSTGRES_URL",
    "DATABASE_URL",
)
DISARMED_FLAGS = {
    "MAINNET": "false",
    "REAL_MONEY": "false",
    "DEMO_AUTONOMOUS_ENABLED": "false",
    "AUTONOMOUS_SEND": "false",
    "EXCHANGE_WRITE": "false",
}


class ReadOnlyExchangeClient:
    """Refuse every Demo write path while forwarding official reads."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.write_call_count = 0
        self.create_order_calls = 0

    def __getattr__(self, name: str) -> Any:
        if name in WRITE_METHODS:

            def _blocked(*_args: Any, **_kwargs: Any) -> Any:
                self.write_call_count += 1
                self.create_order_calls += 1
                raise RuntimeError(f"exchange_write_blocked:{name}")

            return _blocked
        return getattr(self._inner, name)


def _d(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _full(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _prefix(value: Any, n: int = 8) -> str:
    text = str(value or "")
    return text[:n] if text else ""


def _qty_eq(left: Any, right: Any) -> bool:
    return _d(left).quantize(Decimal("0.00000001")) == _d(right).quantize(Decimal("0.00000001"))


def _num_eq(left: Any, right: Any) -> bool:
    if left in (None, "") or right in (None, ""):
        return left in (None, "") and right in (None, "")
    return _full(_d(left)) == _full(_d(right))


def _is_filled(order: dict[str, Any] | None) -> bool:
    if not order:
        return False
    status = str(order.get("orderStatus") or order.get("status") or "").lower()
    return status == "filled"


def _position_size(row: dict[str, Any]) -> Decimal:
    return abs(_d(row.get("size") or 0))


def _target_hash(entry: dict[str, Any], close: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(entry.get("trade_id") or ""),
            str(entry.get("decision_id") or ""),
            str(entry.get("bybit_order_id") or ""),
            str(close.get("bybit_order_id") or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _lifecycle_closed_or_filled(state: str) -> bool:
    return str(state or "") in {"FILLED", "CLOSE_PENDING", "CLOSED"}


def identify_run8_target(intents: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve exactly one unfinished P1 accounting candidate. Never 'latest trade'."""
    campaign = [row for row in intents if str(row.get("campaign_id") or "") == P1_CAMPAIGN_ID]
    entries = [row for row in campaign if not bool(row.get("reduce_only"))]
    closes = [row for row in campaign if bool(row.get("reduce_only"))]
    unfinished: list[dict[str, Any]] = []
    finished: list[dict[str, Any]] = []
    for entry in entries:
        children = [
            row
            for row in closes
            if str(row.get("parent_order_intent_id") or "") == str(entry.get("order_intent_id") or "")
            and str(row.get("trade_id") or "") == str(entry.get("trade_id") or "")
            and str(row.get("decision_id") or "") == str(entry.get("decision_id") or "")
        ]
        if len(children) != 1:
            continue
        close = children[0]
        if not str(entry.get("bybit_order_id") or "") or not str(close.get("bybit_order_id") or ""):
            continue
        if not _lifecycle_closed_or_filled(str(entry.get("state") or "")):
            continue
        if str(close.get("state") or "") not in {"FILLED", "CLOSED"}:
            continue
        pair = {"entry": entry, "close": close}
        exchange_done = is_exchange_backed_provenance(entry.get("pnl_provenance")) and not realized_pnl_absent(
            entry.get("realized_demo_pnl")
        )
        if exchange_done:
            finished.append(pair)
        else:
            unfinished.append(pair)
    if len(unfinished) == 1:
        pair = unfinished[0]
        return {
            "ok": True,
            "candidate_count": 1,
            "entry": pair["entry"],
            "close": pair["close"],
            "idempotent_existing": False,
            "target_identity_hash": _target_hash(pair["entry"], pair["close"]),
        }
    if len(unfinished) == 0 and len(finished) == 1:
        pair = finished[0]
        return {
            "ok": True,
            "candidate_count": 1,
            "entry": pair["entry"],
            "close": pair["close"],
            "idempotent_existing": True,
            "target_identity_hash": _target_hash(pair["entry"], pair["close"]),
        }
    return {
        "ok": False,
        "candidate_count": len(unfinished) if unfinished else len(finished),
        "entry": None,
        "close": None,
        "idempotent_existing": False,
        "target_identity_hash": None,
    }


def identify_latest_p1_lifecycle(intents: list[dict[str, Any]]) -> dict[str, Any] | None:
    resolved = identify_run8_target(intents)
    if not resolved.get("ok"):
        return None
    return {"entry": resolved["entry"], "close": resolved["close"]}


def accounting_conflicts(existing: dict[str, Any], recovered: dict[str, Any]) -> list[str]:
    """Conflict only when an existing exchange-sourced record disagrees with Bybit truth."""
    conflicts: list[str] = []
    existing_provenance = existing.get("pnl_provenance")
    if not is_exchange_backed_provenance(existing_provenance):
        if realized_pnl_absent(existing.get("realized_demo_pnl")) and is_provisional_provenance(existing_provenance):
            return []
        if realized_pnl_absent(existing.get("realized_demo_pnl")):
            return []
        return []
    mapping = (
        ("actual_entry_price", "actual_entry_price"),
        ("actual_exit_price", "actual_exit_price"),
        ("realized_demo_pnl", "realized_demo_pnl"),
        ("pnl_provenance", "pnl_provenance"),
    )
    for existing_key, recovered_key in mapping:
        current = existing.get(existing_key)
        incoming = recovered.get(recovered_key)
        if current in (None, "", {}) or incoming in (None, ""):
            continue
        if existing_key == "pnl_provenance":
            if str(current) != str(incoming) and is_exchange_backed_provenance(current):
                conflicts.append(existing_key)
        elif not _num_eq(current, incoming):
            conflicts.append(existing_key)
    return conflicts


def poll_closed_pnl(
    client: Any,
    *,
    symbol: str,
    close_order_id: str,
    sleep: Callable[[float], None],
    interval_sec: float = POLL_INTERVAL_SEC,
    timeout_sec: float = POLL_TIMEOUT_SEC,
    time_fn: Callable[[], float] = time.time,
) -> tuple[dict[str, Any] | None, int]:
    deadline = time_fn() + timeout_sec
    attempts = 0
    while True:
        attempts += 1
        rows = list(client.list_closed_pnl(symbol=symbol, limit=50) or [])
        matched = match_closed_pnl_by_close_order_id(rows, close_order_id)
        if matched is not None:
            return matched, attempts
        if time_fn() >= deadline:
            return None, attempts
        sleep(interval_sec)


def _base_evidence() -> dict[str, Any]:
    return {
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": "HOLD",
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": "HOLD",
        "P1_PREFLIGHT_PASS": True,
        "P1_ENTRY_RECONCILIATION_PASS": False,
        "P1_CLOSE_RECONCILIATION_PASS": False,
        "P1_EXCHANGE_REALIZED_PNL_PASS": False,
        "P1_DURABLE_LEDGER_LIFECYCLE_PASS": False,
        "P1_RUN8_ENTRY_EXCHANGE_CONFIRMED": False,
        "P1_RUN8_CLOSE_EXCHANGE_CONFIRMED": False,
        "P1_RUN8_POSITION_FLAT": False,
        "P1_RUN8_EXACT_CLOSED_PNL_MATCH": False,
        "P1_RUN8_LEDGER_FINALIZED": False,
        "run8_trade_already_occurred": True,
        "read_only_exchange": True,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "ledger_only_finalization": True,
        "exact_closed_pnl_identity_rule": "closed_pnl.orderId==run8_close_bybit_orderId",
        "pnl_provenance": None,
        "ledger_final_state": None,
        "recovery_stage": "TARGET_RESOLUTION",
        "runtime_code_identity_pass": False,
        "expected_sha_prefix": "",
        "baked_sha_prefix": "",
        "source_sha_prefix": "",
        "runtime_code_identity_pass": False,
        "expected_sha_prefix": "",
        "baked_sha_prefix": "",
        "source_sha_prefix": "",
        "candidate_count": 0,
        "entry_read_pass": False,
        "close_read_pass": False,
        "position_flat": False,
        "execution_identity_pass": False,
        "closed_pnl_exact_match": False,
        "ledger_finalization_pass": False,
        "exception_type": None,
        "error": None,
    }


def _close_intent(ledger: Any, intent_id: str, current_state: str) -> None:
    if current_state in {"CLOSED", "CANCELLED", "REJECTED"}:
        return
    try:
        ledger.transition(intent_id, "CLOSED", source="p1_run8_accounting_recovery")
        return
    except ValueError:
        pass
    if current_state == "FILLED":
        ledger.transition(intent_id, "CLOSE_PENDING", source="p1_run8_accounting_recovery")
        ledger.transition(intent_id, "CLOSED", source="p1_run8_accounting_recovery")


def _merge_proven_identity(evidence: dict[str, Any], proven: dict[str, Any] | None) -> dict[str, Any]:
    if not proven:
        return evidence
    passed = bool(
        proven.get("runtime_code_identity_pass")
        or proven.get("runtime_code_identity_pass")
        or proven.get("code_identity_pass")
    )
    if passed:
        evidence["runtime_code_identity_pass"] = True
        evidence["runtime_code_identity_pass"] = True
        evidence["code_identity_pass"] = True
    expected = proven.get("expected_sha_prefix") or proven.get("expected_sha_prefix") or ""
    baked = proven.get("baked_sha_prefix") or proven.get("baked_sha_prefix") or ""
    source = proven.get("source_sha_prefix") or proven.get("source_sha_prefix") or ""
    if expected:
        evidence["expected_sha_prefix"] = expected
        evidence["expected_sha_prefix"] = expected
    if baked:
        evidence["baked_sha_prefix"] = baked
        evidence["baked_sha_prefix"] = baked
    if source:
        evidence["source_sha_prefix"] = source
        evidence["source_sha_prefix"] = source
    return evidence


def recover_run8_accounting(
    *,
    client: Any,
    ledger: Any,
    sleep: Callable[[float], None] = time.sleep,
    time_fn: Callable[[], float] = time.time,
    poll_interval_sec: float = POLL_INTERVAL_SEC,
    poll_timeout_sec: float = POLL_TIMEOUT_SEC,
    proven_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = _merge_proven_identity(_base_evidence(), proven_identity)
    guarded = client if isinstance(client, ReadOnlyExchangeClient) else ReadOnlyExchangeClient(client)

    def _hold(reason: str, *, stage: str | None = None) -> dict[str, Any]:
        if stage:
            evidence["recovery_stage"] = stage
        evidence["error"] = reason
        evidence["create_order_calls"] = int(getattr(guarded, "create_order_calls", 0) or 0)
        evidence["exchange_write_call_count"] = int(getattr(guarded, "write_call_count", 0) or 0)
        evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] = "HOLD"
        evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] = "HOLD"
        return sanitize_evidence(evidence)

    try:
        evidence["recovery_stage"] = "TARGET_RESOLUTION"
        intents = list(ledger.list_campaign_intents(P1_CAMPAIGN_ID) or [])
        resolved = identify_run8_target(intents)
        evidence["candidate_count"] = int(resolved.get("candidate_count") or 0)
        if not resolved.get("ok"):
            return _hold("run8_trade_identity_missing", stage="TARGET_RESOLUTION")
        entry = dict(resolved["entry"])
        close = dict(resolved["close"])
        evidence["target_identity_hash"] = resolved.get("target_identity_hash")
        symbol = str(entry.get("symbol") or "")
        side = str(entry.get("side") or "")
        entry_order_id = str(entry.get("bybit_order_id") or "")
        close_order_id = str(close.get("bybit_order_id") or "")
        entry_link_id = str(entry.get("order_link_id") or "")
        close_link_id = str(close.get("order_link_id") or "")
        requested_qty = str(entry.get("requested_qty") or "")
        evidence.update(
            {
                "symbol": symbol,
                "side": side,
                "requested_qty": requested_qty,
                "decision_id_prefix": _prefix(entry.get("decision_id")),
                "trade_id_prefix": _prefix(entry.get("trade_id")),
                "entry_order_intent_id_prefix": _prefix(entry.get("order_intent_id")),
                "close_order_intent_id_prefix": _prefix(close.get("order_intent_id")),
                "entry_orderLinkId_prefix": _prefix(entry_link_id),
                "close_orderLinkId_prefix": _prefix(close_link_id),
                "entry_orderId_prefix": _prefix(entry_order_id),
                "close_orderId_prefix": _prefix(close_order_id),
            }
        )

        evidence["recovery_stage"] = "ENTRY_ORDER_READ"
        entry_order = guarded.find_order(symbol=symbol, order_id=entry_order_id, order_link_id=entry_link_id)
        evidence["recovery_stage"] = "CLOSE_ORDER_READ"
        close_order = guarded.find_order(symbol=symbol, order_id=close_order_id, order_link_id=close_link_id)
        entry_filled = _is_filled(entry_order)
        close_filled = _is_filled(close_order)
        evidence["entry_read_pass"] = entry_filled
        evidence["close_read_pass"] = close_filled
        evidence["P1_RUN8_ENTRY_EXCHANGE_CONFIRMED"] = entry_filled
        evidence["P1_RUN8_CLOSE_EXCHANGE_CONFIRMED"] = close_filled
        evidence["P1_ENTRY_RECONCILIATION_PASS"] = entry_filled
        evidence["P1_CLOSE_RECONCILIATION_PASS"] = close_filled
        if not entry_filled:
            return _hold("entry_order_not_filled", stage="ENTRY_ORDER_READ")
        if not close_filled:
            return _hold("close_order_not_filled", stage="CLOSE_ORDER_READ")

        evidence["recovery_stage"] = "POSITION_READ"
        positions = list(guarded.list_positions(symbol) or [])
        open_size = sum(_position_size(row) for row in positions)
        open_orders = list(guarded.list_open_orders(symbol) or [])
        p1_open = [
            row
            for row in open_orders
            if str(row.get("orderLinkId") or "") in {entry_link_id, close_link_id}
            or str(row.get("orderId") or "") in {entry_order_id, close_order_id}
        ]
        flat = open_size == 0 and not p1_open
        evidence["position_flat"] = flat
        evidence["P1_RUN8_POSITION_FLAT"] = flat
        evidence["position_after_close"] = "0" if flat else str(open_size)
        if open_size != 0:
            return _hold("position_not_flat", stage="POSITION_READ")
        if p1_open:
            return _hold("p1_open_order_remaining", stage="POSITION_READ")

        evidence["recovery_stage"] = "EXECUTION_READ"
        entry_execs = list_executions_for_order(guarded, symbol=symbol, order_id=entry_order_id)
        close_execs = list_executions_for_order(guarded, symbol=symbol, order_id=close_order_id)
        entry_fills = aggregate_executions(entry_execs, entry_order_id)
        close_fills = aggregate_executions(close_execs, close_order_id)
        evidence["execution_identity_pass"] = entry_fills["count"] > 0 and close_fills["count"] > 0
        if entry_fills["count"] == 0 or close_fills["count"] == 0:
            return _hold("execution_identity_missing", stage="EXECUTION_READ")
        if requested_qty and not _qty_eq(entry_fills["qty"], requested_qty):
            return _hold("entry_fill_qty_mismatch", stage="EXECUTION_READ")
        if not _qty_eq(close_fills["qty"], entry_fills["qty"]):
            return _hold("close_fill_qty_mismatch", stage="EXECUTION_READ")

        evidence["recovery_stage"] = "CLOSED_PNL_READ"
        now_ms = int(time_fn() * 1000)
        close_anchor = None
        for key in ("updatedTime", "createdTime", "closed_at", "created_at"):
            raw = (close_order or {}).get(key) or close.get(key)
            if raw not in (None, ""):
                try:
                    close_anchor = int(float(raw))
                    if close_anchor < 10_000_000_000:
                        close_anchor *= 1000
                    break
                except (TypeError, ValueError):
                    close_anchor = None
        start_ms, end_ms = bounded_window_ms(close_anchor, now_ms=now_ms)
        pnl_row, attempts = poll_exact_closed_pnl(
            guarded,
            symbol=symbol,
            close_order_id=close_order_id,
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            sleep=sleep,
            time_fn=time_fn,
            interval_sec=poll_interval_sec,
            timeout_sec=poll_timeout_sec,
        )
        evidence["closed_pnl_poll_attempts"] = attempts
        if pnl_row is None:
            return _hold("exact_closed_pnl_unavailable", stage="CLOSED_PNL_READ")
        evidence["closed_pnl_exact_match"] = True
        evidence["P1_RUN8_EXACT_CLOSED_PNL_MATCH"] = True
        evidence["P1_EXCHANGE_REALIZED_PNL_PASS"] = True
        closed_qty = (
            pnl_row.get("closedSize")
            or pnl_row.get("closedSize")
            or pnl_row.get("qty")
            or close_fills["qty"]
        )
        if not _qty_eq(closed_qty, close_fills["qty"]):
            return _hold("closed_pnl_qty_mismatch")

        actual_entry = pnl_row.get("avgEntryPrice") or pnl_row.get("avgEntryPrice") or entry_fills["vwap"]
        actual_exit = pnl_row.get("avgExitPrice") or pnl_row.get("avgExitPrice") or close_fills["vwap"]
        open_fee = pnl_row.get("openFee")
        close_fee = pnl_row.get("closeFee")
        if open_fee in (None, ""):
            open_fee = entry_fills["fee"]
        if close_fee in (None, ""):
            close_fee = close_fills["fee"]
        realized = pnl_row.get("closedPnl")
        try:
            closed_at_dt, closed_at_source, closed_at_ms = closed_at_from_closed_pnl_row(pnl_row)
        except ClosedAtError:
            return _hold("closed_at_invalid", stage="LEDGER_FINALIZATION")
        recovered = {
            "actual_entry_price": _full(_d(actual_entry)) if actual_entry not in (None, "") else None,
            "actual_exit_price": _full(_d(actual_exit)) if actual_exit not in (None, "") else None,
            "actual_qty": _full(_d(closed_qty)),
            "open_fee": _full(_d(open_fee)),
            "close_fee": _full(_d(close_fee)),
            "realized_demo_pnl": _full(_d(realized)) if realized not in (None, "") else None,
            "closed_at": closed_at_dt,
            "closed_at_utc": closed_at_dt.isoformat(),
            "closed_at_source": closed_at_source,
            "closed_at_exchange_ms": closed_at_ms,
            "pnl_provenance": PNL_PROVENANCE,
        }
        if recovered["realized_demo_pnl"] is None:
            return _hold("closed_pnl_missing_closedPnl")

        evidence.update(
            {
                "filled_qty": recovered["actual_qty"],
                "actual_entry_price": recovered["actual_entry_price"],
                "actual_exit_price": recovered["actual_exit_price"],
                "open_fee": recovered["open_fee"],
                "close_fee": recovered["close_fee"],
                "realized_demo_pnl": recovered["realized_demo_pnl"],
                "pnl_provenance": PNL_PROVENANCE,
                "closed_at_utc": recovered["closed_at_utc"],
                "closed_at_source": recovered["closed_at_source"],
            }
        )

        evidence["recovery_stage"] = "LEDGER_FINALIZATION"
        latest_entry = ledger.get_intent(str(entry.get("order_intent_id"))) or entry
        conflicts = accounting_conflicts(latest_entry, recovered)
        if conflicts:
            evidence["evidence_conflict_fields"] = conflicts
            return _hold("exchange_ledger_evidence_conflict", stage="LEDGER_FINALIZATION")

        already_final = (
            str(latest_entry.get("state") or "") == "CLOSED"
            and str(latest_entry.get("pnl_provenance") or "") == PNL_PROVENANCE
            and _num_eq(latest_entry.get("realized_demo_pnl"), recovered["realized_demo_pnl"])
        )
        if not already_final:
            try:
                ledger.record_accounting(
                    str(entry.get("order_intent_id")),
                    actual_entry_price=recovered["actual_entry_price"],
                    actual_exit_price=recovered["actual_exit_price"],
                    fees=_full(_d(recovered["open_fee"]) + _d(recovered["close_fee"])),
                    realized_demo_pnl=recovered["realized_demo_pnl"],
                    closed_at=recovered["closed_at"],
                    pnl_provenance=PNL_PROVENANCE,
                    accounting={
                        "actual_qty": recovered["actual_qty"],
                        "open_fee": recovered["open_fee"],
                        "close_fee": recovered["close_fee"],
                        "pnl_provenance": PNL_PROVENANCE,
                        "close_bybit_order_id_prefix": _prefix(close_order_id),
                        "exchange_realized": True,
                        "closed_at_exchange_ms": recovered["closed_at_exchange_ms"],
                        "closed_at_source": recovered["closed_at_source"],
                        "closed_at_utc": recovered["closed_at_utc"],
                    },
                )
            except ClosedAtError:
                return _hold("closed_at_invalid", stage="LEDGER_FINALIZATION")
            _close_intent(ledger, str(entry.get("order_intent_id")), str(latest_entry.get("state") or ""))
            close_state = str((ledger.get_intent(str(close.get("order_intent_id"))) or close).get("state") or "")
            _close_intent(ledger, str(close.get("order_intent_id")), close_state)

        finalized = ledger.get_intent(str(entry.get("order_intent_id"))) or {}
        ledger_state = str(finalized.get("state") or "")
        lifecycle_ok = ledger_state == "CLOSED" and str(finalized.get("pnl_provenance") or "") == PNL_PROVENANCE
        evidence["ledger_final_state"] = ledger_state
        evidence["P1_RUN8_LEDGER_FINALIZED"] = lifecycle_ok
        evidence["P1_DURABLE_LEDGER_LIFECYCLE_PASS"] = lifecycle_ok
        evidence["ledger_finalization_pass"] = lifecycle_ok
        if not lifecycle_ok:
            return _hold("ledger_lifecycle_not_closed", stage="LEDGER_FINALIZATION")

        evidence["create_order_calls"] = int(getattr(guarded, "create_order_calls", 0) or 0)
        evidence["exchange_write_call_count"] = int(getattr(guarded, "write_call_count", 0) or 0)
        evidence["idempotent"] = already_final
        evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] = "HOLD"
        all_pass = (
            evidence["P1_PREFLIGHT_PASS"]
            and evidence["P1_ENTRY_RECONCILIATION_PASS"]
            and evidence["P1_CLOSE_RECONCILIATION_PASS"]
            and evidence["P1_EXCHANGE_REALIZED_PNL_PASS"]
            and evidence["P1_DURABLE_LEDGER_LIFECYCLE_PASS"]
            and evidence["P1_RUN8_POSITION_FLAT"]
            and ledger_state == "CLOSED"
            and evidence["create_order_calls"] == 0
        )
        evidence["recovery_stage"] = "POOL_CLOSE"
        evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] = "PASS" if all_pass else "HOLD"
        return sanitize_evidence(evidence)
    except Exception as exc:  # noqa: BLE001
        evidence["exception_type"] = type(exc).__name__
        return _hold("recovery_failed")


def _postgres_url() -> str:
    return (os.environ.get("NEXUS_POSTGRES_URL") or os.environ.get("DATABASE_URL") or "").strip()


def _write_evidence(payload: dict[str, Any]) -> None:
    destination = Path(os.environ.get("P1_EVIDENCE_PATH") or "/tmp/nexus_demo_validation/p1_run8_accounting_recovery.json")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except OSError:
        return
    local = Path("artifacts") / "bybit_demo_p1" / "p1_run8_accounting_recovery_evidence.json"
    try:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except OSError:
        return


def _normalize_sha(value: str) -> str:
    return "".join(ch for ch in (value or "").strip().lower() if ch in "0123456789abcdef")


def _is_full_sha(value: str) -> bool:
    return len(value) >= 40 and all(ch in "0123456789abcdef" for ch in value)


def _sha_prefix(value: str, length: int = IDENTITY_PREFIX_LEN) -> str:
    return _normalize_sha(value)[:length]


def evaluate_run8_baked_code_identity(*, expected_sha: str | None = None) -> dict[str, Any]:
    """Authority is baked /app commit files, not workflow-injected env labels.

    When full SHAs exist, pass requires expected == baked == source (full match).
    12-char prefixes are evidence/display only.
    """
    expected = (
        expected_sha
        or os.environ.get("NEXUS_EXPECTED_SHA")
        or os.environ.get("GITHUB_SHA")
        or ""
    ).strip()
    baked, baked_origin = read_container_baked_commit()
    source, source_origin = read_container_source_commit()
    expected_full = _normalize_sha(expected)
    baked_full = _normalize_sha(baked)
    source_full = _normalize_sha(source)
    expected_prefix = expected_full[:IDENTITY_PREFIX_LEN]
    baked_prefix = baked_full[:IDENTITY_PREFIX_LEN]
    source_prefix = source_full[:IDENTITY_PREFIX_LEN]
    baked_file_present = "DEPLOYMENT_COMMIT" in str(baked_origin)
    source_file_present = "SOURCE_COMMIT" in str(source_origin)
    if not baked_file_present or not baked_full:
        reason = "baked_commit_missing"
        passed = False
    elif not source_file_present or not source_full:
        reason = "source_commit_missing"
        passed = False
    elif not _is_full_sha(expected_full) or not _is_full_sha(baked_full) or not _is_full_sha(source_full):
        reason = "malformed_sha"
        passed = False
    elif baked_full != source_full:
        reason = "baked_source_mismatch"
        passed = False
    elif baked_full != expected_full or source_full != expected_full:
        reason = "baked_expected_mismatch"
        passed = False
    else:
        reason = None
        passed = True
    return {
        "runtime_code_identity_pass": passed,
        "expected_sha_prefix": expected_prefix,
        "baked_sha_prefix": baked_prefix,
        "source_sha_prefix": source_prefix,
        "error": reason,
    }


def run_recovery() -> dict[str, Any]:
    return run_recovery_with_probes()


def run_recovery_with_probes() -> dict[str, Any]:
    apply_disarmed_flags()
    evidence = _base_evidence()
    evidence["recovery_stage"] = "CODE_IDENTITY"
    identity = evaluate_run8_baked_code_identity()
    evidence["runtime_code_identity_pass"] = bool(identity.get("runtime_code_identity_pass"))
    evidence["expected_sha_prefix"] = identity.get("expected_sha_prefix") or ""
    evidence["baked_sha_prefix"] = identity.get("baked_sha_prefix") or ""
    evidence["source_sha_prefix"] = identity.get("source_sha_prefix") or ""
    evidence["code_identity_pass"] = evidence["runtime_code_identity_pass"]
    if not evidence["runtime_code_identity_pass"]:
        evidence["error"] = str(identity.get("error") or "code_identity_mismatch")
        evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] = "HOLD"
        evidence["create_order_calls"] = 0
        evidence["exchange_write_call_count"] = 0
        return sanitize_evidence(evidence)

    evidence["recovery_stage"] = "MODULE_IMPORT"
    try:
        from backend.nexus_demo_execution.demo_write_client import DemoWriteClient as _DemoWriteClient
        from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger as _DurableOrderLedger
    except Exception as exc:  # noqa: BLE001
        evidence["exception_type"] = exception_type_name(exc)
        evidence["error"] = "module_import_failed"
        return sanitize_evidence(evidence)

    evidence["recovery_stage"] = "POSTGRES_CONNECT"
    url = _postgres_url()
    if not url:
        evidence["error"] = "ledger_dsn_missing"
        return sanitize_evidence(evidence)
    from backend.nexus_persistence_pg.pool import PostgresPool

    pool = PostgresPool(url)
    try:
        pool.open()
    except Exception as exc:  # noqa: BLE001
        evidence["exception_type"] = exception_type_name(exc)
        evidence["error"] = "postgres_connect_failed"
        return sanitize_evidence(evidence)

    result = sanitize_evidence(evidence)
    try:
        evidence["recovery_stage"] = "POSTGRES_SELECT_1"
        probe = pool.fetchval("SELECT 1")
        if int(probe or 0) != 1:
            evidence["error"] = "postgres_select_1_failed"
            result = sanitize_evidence(evidence)
        else:
            evidence["recovery_stage"] = "LEDGER_CONSTRUCT"
            ledger = _DurableOrderLedger(pool)
            present = ledger.required_migrations_present()
            evidence["migration_0005"] = bool(present.get("migration_0005_present"))
            evidence["migration_0006"] = bool(present.get("migration_0006_present"))
            if not present.get("migration_0005_present") or not present.get("migration_0006_present"):
                evidence["error"] = "required_migrations_missing"
                result = sanitize_evidence(evidence)
            else:
                evidence["recovery_stage"] = "BYBIT_CLIENT_CONSTRUCT"
                client = ReadOnlyExchangeClient(_DemoWriteClient())
                proven = {
                    "runtime_code_identity_pass": bool(
                        evidence.get("runtime_code_identity_pass") or evidence.get("runtime_code_identity_pass")
                    ),
                    "code_identity_pass": bool(evidence.get("code_identity_pass")),
                    "expected_sha_prefix": evidence.get("expected_sha_prefix") or evidence.get("expected_sha_prefix") or "",
                    "baked_sha_prefix": evidence.get("baked_sha_prefix") or evidence.get("baked_sha_prefix") or "",
                    "source_sha_prefix": evidence.get("source_sha_prefix") or evidence.get("source_sha_prefix") or "",
                }
                result = recover_run8_accounting(client=client, ledger=ledger, proven_identity=proven)
                result = _merge_proven_identity(result, proven)
                result = _merge_proven_identity(result, evidence)
    except Exception as exc:  # noqa: BLE001
        evidence["exception_type"] = exception_type_name(exc)
        evidence["error"] = (
            "postgres_select_1_failed" if evidence.get("recovery_stage") == "POSTGRES_SELECT_1" else "recovery_failed"
        )
        evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] = "HOLD"
        result = sanitize_evidence(evidence)
    try:
        pool.close()
    except Exception as exc:  # noqa: BLE001
        payload = dict(result) if isinstance(result, dict) else dict(evidence)
        payload["recovery_stage"] = "POOL_CLOSE"
        payload["exception_type"] = exception_type_name(exc)
        payload["error"] = "pool_close_failed"
        payload["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] = "HOLD"
        payload["create_order_calls"] = 0
        payload["exchange_write_call_count"] = 0
        payload["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] = "HOLD"
        return sanitize_evidence(payload)
    return result


def main() -> int:
    from backend.nexus_demo_execution.p1_run8_accounting_recovery_bootstrap import main as bootstrap_main

    return bootstrap_main()


if __name__ == "__main__":
    raise SystemExit(main())
