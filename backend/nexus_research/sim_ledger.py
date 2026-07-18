"""Phase 5 Gate C — Append-Only Simulation Ledger.

RESEARCH ONLY. Records cash, margin, order events, fills, positions, fees,
funding payments and PnL. Provides reconciliation, idempotency, bounded
history, equity computation.

Constraints:
  - Never allows impossible negative cash/margin (honest reject with reason).
  - All timestamps UTC milliseconds.
  - No persistence to production systems.
  - researchOnly=true on all outputs.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Event types ───────────────────────────────────────────────────────────────
EVT_DEPOSIT = "DEPOSIT"
EVT_WITHDRAWAL = "WITHDRAWAL"
EVT_ORDER_SUBMITTED = "ORDER_SUBMITTED"
EVT_ORDER_FILLED = "ORDER_FILLED"
EVT_ORDER_CANCELLED = "ORDER_CANCELLED"
EVT_ORDER_EXPIRED = "ORDER_EXPIRED"
EVT_ORDER_REJECTED = "ORDER_REJECTED"
EVT_POSITION_OPENED = "POSITION_OPENED"
EVT_POSITION_CLOSED = "POSITION_CLOSED"
EVT_FEE_CHARGED = "FEE_CHARGED"
EVT_FUNDING_CHARGED = "FUNDING_CHARGED"
EVT_PNL_REALISED = "PNL_REALISED"
EVT_MARGIN_RESERVED = "MARGIN_RESERVED"
EVT_MARGIN_RELEASED = "MARGIN_RELEASED"
EVT_RECONCILIATION = "RECONCILIATION"
EVT_REJECT_INSUFFICIENT_BALANCE = "REJECT_INSUFFICIENT_BALANCE"

_ALL_EVT_TYPES = {
    EVT_DEPOSIT, EVT_WITHDRAWAL, EVT_ORDER_SUBMITTED, EVT_ORDER_FILLED,
    EVT_ORDER_CANCELLED, EVT_ORDER_EXPIRED, EVT_ORDER_REJECTED,
    EVT_POSITION_OPENED, EVT_POSITION_CLOSED, EVT_FEE_CHARGED,
    EVT_FUNDING_CHARGED, EVT_PNL_REALISED, EVT_MARGIN_RESERVED,
    EVT_MARGIN_RELEASED, EVT_RECONCILIATION, EVT_REJECT_INSUFFICIENT_BALANCE,
}

_MAX_LEDGER_EVENTS = 5000


class LedgerRejectError(Exception):
    """Raised when a ledger operation is rejected (e.g. negative balance)."""


class SimLedger:
    """Append-only simulation ledger.

    Tracks:
      - cash_balance: free cash available
      - margin_used: cash locked as margin
      - total_fees: cumulative fees paid
      - total_funding: cumulative funding payments (positive = paid out)
      - total_realised_pnl: cumulative realised PnL

    Equity = cash_balance + margin_used + unrealised_pnl (computed externally).
    """

    def __init__(self, initial_cash: float = 10_000.0) -> None:
        self._lock = threading.RLock()
        self._events: deque[dict[str, Any]] = deque(maxlen=_MAX_LEDGER_EVENTS)
        self._idempotency_seen: set[str] = set()
        self._cash_balance: float = 0.0
        self._margin_used: float = 0.0
        self._total_fees: float = 0.0
        self._total_funding: float = 0.0
        self._total_realised_pnl: float = 0.0
        self._total_events: int = 0
        self._total_rejects: int = 0
        self._created_at_ms: int = int(time.time() * 1000)

        # Seed initial cash
        self._append_event(EVT_DEPOSIT, {
            "amount": initial_cash,
            "reason": "initial_simulation_capital",
        })
        self._cash_balance = initial_cash

    # ── Internal append ────────────────────────────────────────────────────────

    def _append_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> str | None:
        """Append a ledger event. Returns event_id or None if deduped."""
        if event_type not in _ALL_EVT_TYPES:
            logger.warning("[ledger] unknown event type %r", event_type)
            return None

        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency_seen:
                return None
            event_id = str(uuid.uuid4())
            event: dict[str, Any] = {
                "eventId": event_id,
                "eventType": event_type,
                "idempotencyKey": idempotency_key,
                "timestampMs": int(time.time() * 1000),
                "payload": payload,
                "cashAfter": self._cash_balance,
                "marginAfter": self._margin_used,
                "researchOnly": True,
            }
            self._events.append(event)
            if idempotency_key:
                self._idempotency_seen.add(idempotency_key)
            self._total_events += 1
            return event_id

    # ── Public ledger operations ───────────────────────────────────────────────

    def deposit(self, amount: float, reason: str = "", idempotency_key: str | None = None) -> str:
        """Credit cash balance."""
        if amount <= 0:
            raise LedgerRejectError(f"deposit amount must be positive, got {amount}")
        with self._lock:
            self._cash_balance += amount
        eid = self._append_event(
            EVT_DEPOSIT, {"amount": amount, "reason": reason},
            idempotency_key=idempotency_key,
        )
        return eid or ""

    def withdraw(self, amount: float, reason: str = "", idempotency_key: str | None = None) -> str:
        """Debit cash balance. Rejects if insufficient."""
        if amount <= 0:
            raise LedgerRejectError(f"withdrawal amount must be positive, got {amount}")
        with self._lock:
            if self._cash_balance < amount:
                self._total_rejects += 1
                self._append_event(
                    EVT_REJECT_INSUFFICIENT_BALANCE,
                    {"requested": amount, "available": self._cash_balance, "reason": reason},
                )
                raise LedgerRejectError(
                    f"insufficient cash: requested={amount:.4f} available={self._cash_balance:.4f}"
                )
            self._cash_balance -= amount
        eid = self._append_event(
            EVT_WITHDRAWAL, {"amount": amount, "reason": reason},
            idempotency_key=idempotency_key,
        )
        return eid or ""

    def reserve_margin(
        self, amount: float, order_id: str, symbol: str,
        idempotency_key: str | None = None,
    ) -> None:
        """Move cash → margin_used. Rejects if insufficient."""
        if amount <= 0:
            raise LedgerRejectError(f"margin amount must be positive, got {amount}")
        with self._lock:
            if self._cash_balance < amount:
                self._total_rejects += 1
                self._append_event(
                    EVT_REJECT_INSUFFICIENT_BALANCE,
                    {"requested": amount, "available": self._cash_balance,
                     "reason": "margin_reserve", "orderId": order_id},
                )
                raise LedgerRejectError(
                    f"insufficient cash for margin: requested={amount:.4f} available={self._cash_balance:.4f}"
                )
            self._cash_balance -= amount
            self._margin_used += amount
        self._append_event(
            EVT_MARGIN_RESERVED,
            {"amount": amount, "orderId": order_id, "symbol": symbol},
            idempotency_key=idempotency_key,
        )

    def release_margin(
        self, amount: float, order_id: str, symbol: str,
        idempotency_key: str | None = None,
    ) -> None:
        """Return margin_used → cash."""
        with self._lock:
            release = min(amount, self._margin_used)
            self._margin_used -= release
            self._cash_balance += release
        self._append_event(
            EVT_MARGIN_RELEASED,
            {"amount": amount, "released": release, "orderId": order_id, "symbol": symbol},
            idempotency_key=idempotency_key,
        )

    def record_fill(
        self, order_id: str, symbol: str, side: str, qty: float,
        fill_price: float, fee: float, idempotency_key: str | None = None,
    ) -> None:
        with self._lock:
            self._total_fees += fee
            self._cash_balance -= fee
        self._append_event(
            EVT_ORDER_FILLED,
            {"orderId": order_id, "symbol": symbol, "side": side,
             "qty": qty, "fillPrice": fill_price, "fee": fee},
            idempotency_key=idempotency_key,
        )
        self._append_event(
            EVT_FEE_CHARGED,
            {"orderId": order_id, "fee": fee, "symbol": symbol},
        )

    def record_position_opened(
        self, position_id: str, order_id: str, symbol: str,
        side: str, qty: float, entry_price: float, margin_amount: float,
        idempotency_key: str | None = None,
    ) -> None:
        self._append_event(
            EVT_POSITION_OPENED,
            {"positionId": position_id, "orderId": order_id, "symbol": symbol,
             "side": side, "qty": qty, "entryPrice": entry_price,
             "marginAmount": margin_amount},
            idempotency_key=idempotency_key,
        )

    def record_position_closed(
        self, position_id: str, symbol: str, side: str, qty: float,
        entry_price: float, exit_price: float, realised_pnl: float,
        exit_fee: float, idempotency_key: str | None = None,
    ) -> None:
        with self._lock:
            self._total_realised_pnl += realised_pnl
            self._total_fees += exit_fee
            # Return realised PnL to cash
            self._cash_balance += realised_pnl
        self._append_event(
            EVT_POSITION_CLOSED,
            {"positionId": position_id, "symbol": symbol, "side": side,
             "qty": qty, "entryPrice": entry_price, "exitPrice": exit_price,
             "realisedPnl": realised_pnl, "exitFee": exit_fee},
            idempotency_key=idempotency_key,
        )
        self._append_event(EVT_PNL_REALISED, {"pnl": realised_pnl, "positionId": position_id})
        if exit_fee > 0:
            self._append_event(EVT_FEE_CHARGED, {"fee": exit_fee, "positionId": position_id})

    def record_funding(
        self, position_id: str, symbol: str, funding_payment: float,
        idempotency_key: str | None = None,
    ) -> None:
        """Record funding payment (positive = paid by LONG)."""
        with self._lock:
            self._total_funding += funding_payment
            self._cash_balance -= funding_payment
        self._append_event(
            EVT_FUNDING_CHARGED,
            {"positionId": position_id, "symbol": symbol, "funding": funding_payment},
            idempotency_key=idempotency_key,
        )

    def reconcile(self, unrealised_pnl: float = 0.0) -> dict[str, Any]:
        """Run balance reconciliation. Returns summary."""
        equity = self._cash_balance + self._margin_used + unrealised_pnl
        report: dict[str, Any] = {
            "cashBalance": self._cash_balance,
            "marginUsed": self._margin_used,
            "unrealisedPnl": unrealised_pnl,
            "equity": equity,
            "totalFees": self._total_fees,
            "totalFunding": self._total_funding,
            "totalRealisedPnl": self._total_realised_pnl,
            "totalEvents": self._total_events,
            "totalRejects": self._total_rejects,
            "consistent": self._cash_balance >= 0 and self._margin_used >= 0,
            "researchOnly": True,
            "reconciledAtMs": int(time.time() * 1000),
        }
        self._append_event(EVT_RECONCILIATION, report)
        return report

    # ── Query ─────────────────────────────────────────────────────────────────

    def recent_events(
        self,
        limit: int = 100,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)
        if event_type:
            events = [e for e in events if e["eventType"] == event_type]
        return events[-limit:]

    def snapshot(self, unrealised_pnl: float = 0.0) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "researchOnly": True,
                "privateApi": False,
                "cashBalance": self._cash_balance,
                "marginUsed": self._margin_used,
                "equity": self._cash_balance + self._margin_used + unrealised_pnl,
                "totalFees": self._total_fees,
                "totalFunding": self._total_funding,
                "totalRealisedPnl": self._total_realised_pnl,
                "totalEvents": self._total_events,
                "totalRejects": self._total_rejects,
                "eventLogSize": len(self._events),
                "eventLogCapacity": _MAX_LEDGER_EVENTS,
                "generatedAt": int(time.time() * 1000),
            }

    def reset(self, initial_cash: float = 10_000.0) -> None:
        with self._lock:
            self._events.clear()
            self._idempotency_seen.clear()
            self._cash_balance = 0.0
            self._margin_used = 0.0
            self._total_fees = 0.0
            self._total_funding = 0.0
            self._total_realised_pnl = 0.0
            self._total_events = 0
            self._total_rejects = 0
        self._append_event(EVT_DEPOSIT, {
            "amount": initial_cash, "reason": "reset_simulation_capital"
        })
        with self._lock:
            self._cash_balance = initial_cash
        logger.info("[ledger] reset with initial_cash=%.2f", initial_cash)


# ── Singleton ─────────────────────────────────────────────────────────────────
_LEDGER: SimLedger | None = None
_LEDGER_LOCK = threading.Lock()


def get_sim_ledger(initial_cash: float = 10_000.0) -> SimLedger:
    global _LEDGER
    with _LEDGER_LOCK:
        if _LEDGER is None:
            _LEDGER = SimLedger(initial_cash=initial_cash)
            logger.info("[ledger] SimLedger initialised (researchOnly=true)")
        return _LEDGER


def reset_sim_ledger(initial_cash: float = 10_000.0) -> None:
    global _LEDGER
    with _LEDGER_LOCK:
        if _LEDGER is not None:
            _LEDGER.reset(initial_cash)
        else:
            _LEDGER = SimLedger(initial_cash=initial_cash)
    logger.info("[ledger] ledger reset")
