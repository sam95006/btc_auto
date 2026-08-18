"""Founder-dispatch Run #8 post-trade accounting recovery.

Exchange phase is read-only. Ledger finalization writes PostgreSQL only.
Never creates, closes, or cancels an exchange order.
"""
from __future__ import annotations

import json
import os
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient
from backend.nexus_demo_execution.durable_order_ledger import DurableOrderLedger
from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_demo_execution.p1_qualification import P1_CAMPAIGN_ID, sanitize_evidence


CONFIRM_PHRASE = "RECOVER_BYBIT_DEMO_P1_RUN8_ACCOUNTING"
PNL_PROVENANCE = "BYBIT_V5_POSITION_CLOSED_PNL"
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


def identify_latest_p1_lifecycle(intents: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Bind the latest P1 entry/close pair that already has exact Bybit order IDs."""
    campaign = [row for row in intents if str(row.get("campaign_id") or "") == P1_CAMPAIGN_ID]
    entries = [row for row in campaign if not bool(row.get("reduce_only"))]
    closes = [row for row in campaign if bool(row.get("reduce_only"))]
    entries.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    for entry in entries:
        children = [
            row
            for row in closes
            if str(row.get("parent_order_intent_id") or "") == str(entry.get("order_intent_id") or "")
        ]
        children.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        if not children:
            continue
        close = children[0]
        if str(entry.get("bybit_order_id") or "") and str(close.get("bybit_order_id") or ""):
            return {"entry": entry, "close": close}
    return None


def match_closed_pnl_by_close_order_id(rows: list[dict[str, Any]], close_order_id: str) -> dict[str, Any] | None:
    wanted = str(close_order_id or "")
    if not wanted:
        return None
    for row in rows:
        if str(row.get("orderId") or "") == wanted:
            return row
    return None


def aggregate_executions(rows: list[dict[str, Any]], order_id: str) -> dict[str, Any]:
    wanted = str(order_id or "")
    qty = Decimal("0")
    notional = Decimal("0")
    fee = Decimal("0")
    matched = 0
    for row in rows:
        if str(row.get("orderId") or "") != wanted:
            continue
        matched += 1
        exec_qty = _d(row.get("execQty") or row.get("qty"))
        exec_price = _d(row.get("execPrice") or row.get("price"))
        qty += exec_qty
        notional += exec_qty * exec_price
        fee += abs(_d(row.get("execFee") or row.get("fee")))
    return {
        "qty": qty,
        "vwap": (notional / qty) if qty > 0 else None,
        "fee": fee,
        "count": matched,
    }


def accounting_conflicts(existing: dict[str, Any], recovered: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
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
            if str(current) != str(incoming):
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


def recover_run8_accounting(
    *,
    client: Any,
    ledger: Any,
    sleep: Callable[[float], None] = time.sleep,
    time_fn: Callable[[], float] = time.time,
    poll_interval_sec: float = POLL_INTERVAL_SEC,
    poll_timeout_sec: float = POLL_TIMEOUT_SEC,
) -> dict[str, Any]:
    evidence = _base_evidence()
    guarded = client if isinstance(client, ReadOnlyExchangeClient) else ReadOnlyExchangeClient(client)

    def _hold(reason: str) -> dict[str, Any]:
        evidence["error"] = reason
        evidence["create_order_calls"] = int(getattr(guarded, "create_order_calls", 0) or 0)
        evidence["exchange_write_call_count"] = int(getattr(guarded, "write_call_count", 0) or 0)
        evidence["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] = "HOLD"
        evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] = "HOLD"
        return sanitize_evidence(evidence)

    try:
        intents = list(ledger.list_campaign_intents(P1_CAMPAIGN_ID) or [])
        pair = identify_latest_p1_lifecycle(intents)
        if pair is None:
            return _hold("run8_trade_identity_missing")
        entry = dict(pair["entry"])
        close = dict(pair["close"])
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

        entry_order = guarded.find_order(symbol=symbol, order_id=entry_order_id, order_link_id=entry_link_id)
        close_order = guarded.find_order(symbol=symbol, order_id=close_order_id, order_link_id=close_link_id)
        entry_filled = _is_filled(entry_order)
        close_filled = _is_filled(close_order)
        evidence["P1_RUN8_ENTRY_EXCHANGE_CONFIRMED"] = entry_filled
        evidence["P1_RUN8_CLOSE_EXCHANGE_CONFIRMED"] = close_filled
        evidence["P1_ENTRY_RECONCILIATION_PASS"] = entry_filled
        evidence["P1_CLOSE_RECONCILIATION_PASS"] = close_filled
        if not entry_filled:
            return _hold("entry_order_not_filled")
        if not close_filled:
            return _hold("close_order_not_filled")

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
        evidence["P1_RUN8_POSITION_FLAT"] = flat
        evidence["position_after_close"] = "0" if flat else str(open_size)
        if open_size != 0:
            return _hold("position_not_flat")
        if p1_open:
            return _hold("p1_open_order_remaining")

        executions = list(guarded.list_executions(symbol=symbol, limit=100) or [])
        entry_fills = aggregate_executions(executions, entry_order_id)
        close_fills = aggregate_executions(executions, close_order_id)
        if entry_fills["count"] == 0 or close_fills["count"] == 0:
            return _hold("execution_identity_missing")
        if requested_qty and not _qty_eq(entry_fills["qty"], requested_qty):
            return _hold("entry_fill_qty_mismatch")
        if not _qty_eq(close_fills["qty"], entry_fills["qty"]):
            return _hold("close_fill_qty_mismatch")

        pnl_row, attempts = poll_closed_pnl(
            guarded,
            symbol=symbol,
            close_order_id=close_order_id,
            sleep=sleep,
            interval_sec=poll_interval_sec,
            timeout_sec=poll_timeout_sec,
            time_fn=time_fn,
        )
        evidence["closed_pnl_poll_attempts"] = attempts
        if pnl_row is None:
            return _hold("exact_closed_pnl_unavailable")
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
        closed_at = (
            pnl_row.get("updatedTime")
            or pnl_row.get("updatedTime")
            or pnl_row.get("createdTime")
            or pnl_row.get("createdTime")
        )
        recovered = {
            "actual_entry_price": _full(_d(actual_entry)) if actual_entry not in (None, "") else None,
            "actual_exit_price": _full(_d(actual_exit)) if actual_exit not in (None, "") else None,
            "actual_qty": _full(_d(closed_qty)),
            "open_fee": _full(_d(open_fee)),
            "close_fee": _full(_d(close_fee)),
            "realized_demo_pnl": _full(_d(realized)) if realized not in (None, "") else None,
            "closed_at": str(closed_at) if closed_at not in (None, "") else None,
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
            }
        )

        latest_entry = ledger.get_intent(str(entry.get("order_intent_id"))) or entry
        conflicts = accounting_conflicts(latest_entry, recovered)
        if conflicts:
            evidence["evidence_conflict_fields"] = conflicts
            return _hold("exchange_ledger_evidence_conflict")

        already_final = (
            str(latest_entry.get("state") or "") == "CLOSED"
            and str(latest_entry.get("pnl_provenance") or "") == PNL_PROVENANCE
            and _num_eq(latest_entry.get("realized_demo_pnl"), recovered["realized_demo_pnl"])
        )
        if not already_final:
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
                },
            )
            _close_intent(ledger, str(entry.get("order_intent_id")), str(latest_entry.get("state") or ""))
            close_state = str((ledger.get_intent(str(close.get("order_intent_id"))) or close).get("state") or "")
            _close_intent(ledger, str(close.get("order_intent_id")), close_state)

        finalized = ledger.get_intent(str(entry.get("order_intent_id"))) or {}
        ledger_state = str(finalized.get("state") or "")
        lifecycle_ok = ledger_state == "CLOSED" and str(finalized.get("pnl_provenance") or "") == PNL_PROVENANCE
        evidence["ledger_final_state"] = ledger_state
        evidence["P1_RUN8_LEDGER_FINALIZED"] = lifecycle_ok
        evidence["P1_DURABLE_LEDGER_LIFECYCLE_PASS"] = lifecycle_ok
        if not lifecycle_ok:
            return _hold("ledger_lifecycle_not_closed")

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
        evidence["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] = "PASS" if all_pass else "HOLD"
        return sanitize_evidence(evidence)
    except Exception:  # noqa: BLE001
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


def run_recovery() -> dict[str, Any]:
    for key, value in DISARMED_FLAGS.items():
        os.environ[key] = value
    url = _postgres_url()
    if not url:
        evidence = _base_evidence()
        evidence["error"] = "ledger_dsn_missing"
        return sanitize_evidence(evidence)
    from backend.nexus_persistence_pg.pool import PostgresPool

    pool = PostgresPool(url)
    pool.open()
    try:
        client = ReadOnlyExchangeClient(DemoWriteClient())
        ledger = DurableOrderLedger(pool)
        return recover_run8_accounting(client=client, ledger=ledger)
    finally:
        pool.close()


def main() -> int:
    evidence = redact_secrets(run_recovery())
    for key in SECRET_ENV_KEYS:
        evidence.pop(key, None)
    _write_evidence(evidence)
    print(json.dumps(evidence, default=str))
    return 0 if evidence.get("BYBIT_DEMO_SINGLE_TRADE_E2E_PASS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
