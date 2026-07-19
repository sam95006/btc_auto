"""Phase 5/6.1B — Simulation Ledger facade over durable hash-chained SoT.

RESEARCH ONLY. Derived balances come from DurableLedgerAccount replay.
Never reseeds INITIAL_DEPOSIT when durable events already exist.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from backend.nexus_research.durable_ledger import (
    ACCOUNT_PAPER_DEFAULT,
    EVT_FEE_CHARGED as _DL_FEE,
    EVT_FUNDING_CHARGED as _DL_FUNDING,
    EVT_MARGIN_RELEASED as _DL_MARGIN_REL,
    EVT_MARGIN_RESERVED as _DL_MARGIN_RES,
    EVT_ORDER_FILLED as _DL_FILL,
    EVT_PNL_REALIZED as _DL_PNL,
    get_durable_ledger,
    hydration_status,
)

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# Legacy aliases kept for callers / tests
EVT_DEPOSIT = "INITIAL_DEPOSIT"
EVT_WITHDRAWAL = "ADJUSTMENT_VALIDATION_ONLY"
EVT_ORDER_SUBMITTED = "ORDER_FILLED"
EVT_ORDER_FILLED = _DL_FILL
EVT_ORDER_CANCELLED = "ADJUSTMENT_VALIDATION_ONLY"
EVT_ORDER_EXPIRED = "ADJUSTMENT_VALIDATION_ONLY"
EVT_ORDER_REJECTED = "ADJUSTMENT_VALIDATION_ONLY"
EVT_POSITION_OPENED = "ADJUSTMENT_VALIDATION_ONLY"
EVT_POSITION_CLOSED = "ADJUSTMENT_VALIDATION_ONLY"
EVT_FEE_CHARGED = _DL_FEE
EVT_FUNDING_CHARGED = _DL_FUNDING
EVT_PNL_REALISED = _DL_PNL
EVT_MARGIN_RESERVED = _DL_MARGIN_RES
EVT_MARGIN_RELEASED = _DL_MARGIN_REL
EVT_RECONCILIATION = "ADJUSTMENT_VALIDATION_ONLY"
EVT_REJECT_INSUFFICIENT_BALANCE = "ADJUSTMENT_VALIDATION_ONLY"
_MAX_LEDGER_EVENTS = 5000


class LedgerRejectError(Exception):
    """Raised when a ledger operation is rejected (e.g. negative balance)."""


class SimLedger:
    """Facade: public API unchanged; durable ledger is Source of Truth."""

    def __init__(
        self,
        initial_cash: float = 10_000.0,
        account_id: str = ACCOUNT_PAPER_DEFAULT,
    ) -> None:
        self._lock = threading.RLock()
        self._account_id = account_id
        self._initial_cash = initial_cash
        self._total_rejects = 0
        self._created_at_ms = int(time.time() * 1000)
        self._durable = get_durable_ledger(account_id)
        # Ensure initial deposit only if empty (handled inside get_durable_ledger /
        # ensure_initial_deposit). Never force a second seed here.

    @property
    def _cash_balance(self) -> float:
        return float(self._durable.cash)

    @_cash_balance.setter
    def _cash_balance(self, value: float) -> None:
        # Derived-only; ignore external sets except tests.
        pass

    @property
    def _margin_used(self) -> float:
        return float(self._durable.margin)

    @_margin_used.setter
    def _margin_used(self, value: float) -> None:
        pass

    @property
    def _total_fees(self) -> float:
        return float(self._durable.fees)

    @property
    def _total_funding(self) -> float:
        return float(self._durable.funding)

    @property
    def _total_realised_pnl(self) -> float:
        return float(self._durable.realized_pnl)

    @property
    def _total_events(self) -> int:
        return len(self._durable.recent_events(limit=_MAX_LEDGER_EVENTS))

    def _boot_id(self) -> str | None:
        try:
            from backend.nexus_research.boot_identity import get_boot_identity

            return get_boot_identity().get("bootId")
        except Exception:  # noqa: BLE001
            return None

    def _append_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        amount: float | None = None,
    ) -> str | None:
        if hydration_status().get("hydrationFailed"):
            logger.warning("[ledger] append blocked — hydration failed")
            return None
        amt = float(amount if amount is not None else payload.get("amount") or payload.get("fee") or payload.get("funding") or payload.get("pnl") or 0.0)
        ik = idempotency_key or f"auto:{event_type}:{uuid.uuid4()}"
        result = self._durable.append_event(
            event_type=event_type,
            amount=amt,
            idempotency_key=ik,
            boot_id=self._boot_id(),
            payload=payload,
        )
        if not result.get("ok"):
            return None
        return str(result.get("eventId") or "")

    def deposit(self, amount: float, reason: str = "", idempotency_key: str | None = None) -> str:
        if amount <= 0:
            raise LedgerRejectError(f"deposit amount must be positive, got {amount}")
        # Prefer INITIAL_DEPOSIT path only when empty; otherwise adjustment.
        if not self._durable.recent_events(limit=1):
            r = self._durable.ensure_initial_deposit(
                amount=amount, boot_id=self._boot_id()
            )
            return str(r.get("eventId") or r.get("existingEventId") or "")
        eid = self._append_event(
            "ADJUSTMENT_VALIDATION_ONLY",
            {"amount": amount, "reason": reason},
            idempotency_key=idempotency_key or f"deposit:{reason}:{amount}",
            amount=amount,
        )
        return eid or ""

    def withdraw(self, amount: float, reason: str = "", idempotency_key: str | None = None) -> str:
        if amount <= 0:
            raise LedgerRejectError(f"withdrawal amount must be positive, got {amount}")
        if self._durable.cash < amount:
            self._total_rejects += 1
            raise LedgerRejectError(
                f"insufficient cash: requested={amount:.4f} available={self._durable.cash:.4f}"
            )
        eid = self._append_event(
            "ADJUSTMENT_VALIDATION_ONLY",
            {"amount": -amount, "reason": reason},
            idempotency_key=idempotency_key,
            amount=-amount,
        )
        return eid or ""

    def reserve_margin(
        self, amount: float, order_id: str, symbol: str,
        idempotency_key: str | None = None,
    ) -> None:
        if amount <= 0:
            raise LedgerRejectError(f"margin amount must be positive, got {amount}")
        if self._durable.cash < amount:
            self._total_rejects += 1
            raise LedgerRejectError(
                f"insufficient cash for margin: requested={amount:.4f} available={self._durable.cash:.4f}"
            )
        self._append_event(
            EVT_MARGIN_RESERVED,
            {"amount": amount, "orderId": order_id, "symbol": symbol},
            idempotency_key=idempotency_key,
            amount=amount,
        )

    def release_margin(
        self, amount: float, order_id: str, symbol: str,
        idempotency_key: str | None = None,
    ) -> None:
        self._append_event(
            EVT_MARGIN_RELEASED,
            {"amount": amount, "orderId": order_id, "symbol": symbol},
            idempotency_key=idempotency_key,
            amount=amount,
        )

    def record_fill(
        self, order_id: str, symbol: str, side: str, qty: float,
        fill_price: float, fee: float, idempotency_key: str | None = None,
    ) -> None:
        self._append_event(
            EVT_ORDER_FILLED,
            {"orderId": order_id, "symbol": symbol, "side": side,
             "qty": qty, "fillPrice": fill_price, "fee": fee},
            idempotency_key=idempotency_key,
            amount=0.0,
        )
        if fee:
            self._append_event(
                EVT_FEE_CHARGED,
                {"orderId": order_id, "fee": fee, "symbol": symbol},
                idempotency_key=(f"{idempotency_key}:fee" if idempotency_key else None),
                amount=fee,
            )

    def record_position_opened(
        self, position_id: str, order_id: str, symbol: str,
        side: str, qty: float, entry_price: float, margin_amount: float,
        idempotency_key: str | None = None,
    ) -> None:
        self._append_event(
            "ADJUSTMENT_VALIDATION_ONLY",
            {"kind": "POSITION_OPENED", "positionId": position_id, "orderId": order_id,
             "symbol": symbol, "side": side, "qty": qty, "entryPrice": entry_price,
             "marginAmount": margin_amount},
            idempotency_key=idempotency_key,
            amount=0.0,
        )

    def record_position_closed(
        self, position_id: str, symbol: str, side: str, qty: float,
        entry_price: float, exit_price: float, realised_pnl: float,
        exit_fee: float, idempotency_key: str | None = None,
    ) -> None:
        self._append_event(
            EVT_PNL_REALIZED,
            {"positionId": position_id, "symbol": symbol, "side": side,
             "qty": qty, "entryPrice": entry_price, "exitPrice": exit_price,
             "realisedPnl": realised_pnl, "exitFee": exit_fee},
            idempotency_key=idempotency_key,
            amount=realised_pnl,
        )
        if exit_fee > 0:
            self._append_event(
                EVT_FEE_CHARGED,
                {"fee": exit_fee, "positionId": position_id},
                idempotency_key=(f"{idempotency_key}:exit_fee" if idempotency_key else None),
                amount=exit_fee,
            )

    def record_funding(
        self, position_id: str, symbol: str, funding_payment: float,
        idempotency_key: str | None = None,
    ) -> None:
        self._append_event(
            EVT_FUNDING_CHARGED,
            {"positionId": position_id, "symbol": symbol, "funding": funding_payment},
            idempotency_key=idempotency_key,
            amount=funding_payment,
        )

    def reconcile(self, unrealised_pnl: float = 0.0) -> dict[str, Any]:
        snap = self.snapshot(unrealised_pnl=unrealised_pnl)
        return {**snap, "reconciled": True}

    def recent_events(
        self, limit: int = 100, event_type: str | None = None
    ) -> list[dict[str, Any]]:
        events = self._durable.recent_events(limit=limit)
        # Adapt to legacy shape expected by APIs / hash builders.
        out = []
        for e in events:
            out.append({
                "eventId": e.get("eventId"),
                "eventType": e.get("eventType"),
                "idempotencyKey": e.get("idempotencyKey"),
                "timestampMs": e.get("occurredAt"),
                "payload": e.get("payload") or {},
                "cashAfter": None,
                "marginAfter": None,
                "amount": e.get("amount"),
                "sequence": e.get("sequence"),
                "eventHash": e.get("eventHash"),
                "previousEventHash": e.get("previousEventHash"),
                "accountId": e.get("accountId"),
                "researchOnly": True,
            })
        if event_type:
            out = [e for e in out if e.get("eventType") == event_type]
        # Fill cashAfter by replaying for display (does not mutate SoT hashes).
        cash = 0.0
        margin = 0.0
        # Re-read full chain for accurate after balances when limit truncates.
        full = self._durable.recent_events(limit=_MAX_LEDGER_EVENTS)
        cash_map: dict[str, float] = {}
        margin_map: dict[str, float] = {}
        for e in full:
            et = str(e.get("eventType") or "")
            amt = float(e.get("amount") or 0.0)
            if et in ("INITIAL_DEPOSIT", "DEPOSIT"):
                cash += amt
            elif et == "MARGIN_RESERVED":
                cash -= amt
                margin += amt
            elif et == "MARGIN_RELEASED":
                rel = min(amt, margin)
                margin -= rel
                cash += rel
            elif et == "FEE_CHARGED":
                cash -= amt
            elif et == "FUNDING_CHARGED":
                cash -= amt
            elif et in ("PNL_REALIZED", "PNL_REALISED"):
                cash += amt
            elif et == "ADJUSTMENT_VALIDATION_ONLY":
                cash += amt
            cash_map[str(e.get("eventId"))] = cash
            margin_map[str(e.get("eventId"))] = margin
        for e in out:
            eid = str(e.get("eventId") or "")
            e["cashAfter"] = cash_map.get(eid)
            e["marginAfter"] = margin_map.get(eid)
        return out

    def snapshot(self, unrealised_pnl: float = 0.0) -> dict[str, Any]:
        base = self._durable.snapshot()
        hyd = hydration_status()
        return {
            **base,
            "unrealisedPnl": unrealised_pnl,
            "equity": float(base.get("cashBalance") or 0.0)
            + float(base.get("marginUsed") or 0.0)
            + float(unrealised_pnl),
            "totalRejects": self._total_rejects,
            "eventLogCapacity": _MAX_LEDGER_EVENTS,
            "privateApi": False,
            "hydrationFailed": bool(hyd.get("hydrationFailed")),
            "hydrationError": hyd.get("hydrationError"),
        }

    def status(self) -> dict[str, Any]:
        return self.snapshot()

    def reset(self, initial_cash: float = 10_000.0) -> None:
        """Research-only test helper — does NOT wipe durable SQLite events."""
        logger.warning(
            "[ledger] reset() ignored for durable SoT account=%s — use new accountId for isolation",
            self._account_id,
        )


_LEDGER: SimLedger | None = None
_LEDGER_LOCK = threading.Lock()
_LEDGERS: dict[str, SimLedger] = {}


def get_sim_ledger(
    initial_cash: float = 10_000.0,
    account_id: str = ACCOUNT_PAPER_DEFAULT,
) -> SimLedger:
    global _LEDGER
    with _LEDGER_LOCK:
        if account_id not in _LEDGERS:
            _LEDGERS[account_id] = SimLedger(
                initial_cash=initial_cash, account_id=account_id
            )
        if account_id == ACCOUNT_PAPER_DEFAULT:
            _LEDGER = _LEDGERS[account_id]
        return _LEDGERS[account_id]


def reset_sim_ledger(initial_cash: float = 10_000.0) -> None:
    """Test helper — clears in-memory cache only; SQLite events remain."""
    global _LEDGER
    from backend.nexus_research.durable_ledger import reset_durable_ledger_cache

    with _LEDGER_LOCK:
        _LEDGERS.clear()
        reset_durable_ledger_cache()
        _LEDGER = SimLedger(initial_cash=initial_cash)
        _LEDGERS[ACCOUNT_PAPER_DEFAULT] = _LEDGER
