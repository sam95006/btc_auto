"""Phase 6.1B — Durable append-only simulator ledger (hash-chained).

SQLite durable_ledger_events is the Source of Truth.
Derived balances are rebuilt by replay. Never reseed INITIAL_DEPOSIT when
events already exist for an account.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY = True
SCHEMA_VERSION = 1

ACCOUNT_PAPER_DEFAULT = "PAPER_RUNTIME_DEFAULT"
ACCOUNT_PAPER_MAIN_V1 = "NEXUS_PAPER_MAIN_V1"
ACCOUNT_VALIDATION_V1 = "PERSISTENCE_VALIDATION_V1"
ACCOUNT_VALIDATION_V2 = "PERSISTENCE_VALIDATION_V2"

EVT_INITIAL_DEPOSIT = "INITIAL_DEPOSIT"
EVT_MARGIN_RESERVED = "MARGIN_RESERVED"
EVT_MARGIN_RELEASED = "MARGIN_RELEASED"
EVT_ORDER_FILLED = "ORDER_FILLED"
EVT_FEE_CHARGED = "FEE_CHARGED"
EVT_FUNDING_CHARGED = "FUNDING_CHARGED"
EVT_PNL_REALIZED = "PNL_REALIZED"
EVT_ADJUSTMENT_VALIDATION_ONLY = "ADJUSTMENT_VALIDATION_ONLY"
# Legacy aliases accepted on replay only
EVT_DEPOSIT_LEGACY = "DEPOSIT"
EVT_PNL_REALISED_LEGACY = "PNL_REALISED"

_DURABLE_TYPES = {
    EVT_INITIAL_DEPOSIT,
    EVT_MARGIN_RESERVED,
    EVT_MARGIN_RELEASED,
    EVT_ORDER_FILLED,
    EVT_FEE_CHARGED,
    EVT_FUNDING_CHARGED,
    EVT_PNL_REALIZED,
    EVT_ADJUSTMENT_VALIDATION_ONLY,
    EVT_DEPOSIT_LEGACY,
    EVT_PNL_REALISED_LEGACY,
}

SOURCE_PAPER = "PAPER_RUNTIME"
SOURCE_VALIDATION = "PERSISTENCE_VALIDATION"

_LOCK = threading.RLock()
_ACCOUNTS: dict[str, "DurableLedgerAccount"] = {}
_HYDRATION_FAILED = False
_HYDRATION_ERROR: str | None = None


def canonical_dumps(obj: Any) -> str:
    """Stable JSON for hashing — sorted keys, no whitespace variance."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_event_hash(body: dict[str, Any]) -> str:
    """Hash canonical body WITHOUT eventHash field."""
    payload = {k: v for k, v in body.items() if k != "eventHash"}
    return hashlib.sha256(canonical_dumps(payload).encode("utf-8")).hexdigest()


def chain_head_hash(events: list[dict[str, Any]]) -> str | None:
    if not events:
        return None
    return str(events[-1].get("eventHash") or "")


def validate_hash_chain(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate sequence + hash chain. Does not recompute stored eventHash."""
    if not events:
        return {"ok": True, "chainValid": True, "count": 0, "errors": []}
    errors: list[str] = []
    prev_hash: str | None = None
    expected_seq = 1
    for e in events:
        seq = int(e.get("sequence") or 0)
        if seq != expected_seq:
            errors.append(f"sequence_gap expected={expected_seq} got={seq}")
        expected_seq = seq + 1
        stored = str(e.get("eventHash") or "")
        # Verify stored hash matches canonical body (excluding eventHash).
        recomputed = compute_event_hash(e)
        if stored and stored != recomputed:
            errors.append(f"eventHash_mismatch seq={seq} eventId={e.get('eventId')}")
        prev = e.get("previousEventHash")
        if seq == 1:
            if prev not in (None, "", "GENESIS"):
                errors.append(f"seq1_previous_not_genesis eventId={e.get('eventId')}")
        else:
            if str(prev or "") != str(prev_hash or ""):
                errors.append(f"chain_break seq={seq} eventId={e.get('eventId')}")
        prev_hash = stored
    return {
        "ok": len(errors) == 0,
        "chainValid": len(errors) == 0,
        "count": len(events),
        "errors": errors[:20],
        "headHash": chain_head_hash(events),
        "sequenceHead": int(events[-1].get("sequence") or 0) if events else 0,
    }


def _load_account_rows(account_id: str) -> list[dict[str, Any]]:
    from backend.nexus_research.storage import get_research_store

    store = get_research_store()
    # Prefer typed query helper if available.
    getter = getattr(store, "query_ledger_events", None)
    if callable(getter):
        rows = getter(account_id)
    else:
        rows = [
            r
            for r in store.query("durable_ledger_events", limit=5000)
            if str(r.get("accountId") or r.get("account_id") or "") == account_id
        ]
    rows.sort(key=lambda r: int(r.get("sequence") or 0))
    return rows


def _persist_event(record: dict[str, Any]) -> bool:
    from backend.nexus_research.storage import get_research_store

    store = get_research_store()
    writer = getattr(store, "append_ledger_event", None)
    if callable(writer):
        return bool(writer(record))
    store.append("durable_ledger_events", record)
    return True


def mark_hydration_failed(reason: str) -> None:
    global _HYDRATION_FAILED, _HYDRATION_ERROR
    with _LOCK:
        _HYDRATION_FAILED = True
        _HYDRATION_ERROR = reason
    logger.error("[durable_ledger] hydration failed: %s", reason)


def clear_hydration_failed() -> None:
    global _HYDRATION_FAILED, _HYDRATION_ERROR
    with _LOCK:
        _HYDRATION_FAILED = False
        _HYDRATION_ERROR = None


def hydration_status() -> dict[str, Any]:
    with _LOCK:
        return {
            "hydrationFailed": _HYDRATION_FAILED,
            "hydrationError": _HYDRATION_ERROR,
            "researchOnly": True,
        }


class DurableLedgerAccount:
    """Per-account durable ledger with hash chain + derived balances."""

    def __init__(self, account_id: str, source: str = SOURCE_PAPER) -> None:
        self.account_id = account_id
        self.source = source
        self._lock = threading.RLock()
        self._events: list[dict[str, Any]] = []
        self._by_idempotency: dict[str, dict[str, Any]] = {}
        self._by_event_id: dict[str, dict[str, Any]] = {}
        self.cash = 0.0
        self.margin = 0.0
        self.fees = 0.0
        self.funding = 0.0
        self.realized_pnl = 0.0
        self._chain_valid = True
        self._loaded = False

    def load_and_replay(self) -> dict[str, Any]:
        with self._lock:
            rows = _load_account_rows(self.account_id)
            # Ignore V1 failed pre-durable markers (never treat as chain).
            rows = [
                r
                for r in rows
                if str(r.get("validationRound") or "") != "PHASE61_RESTART_PROOF_V1"
                or str(r.get("result") or "") != "FAILED_PRE_DURABLE_LEDGER"
            ]
            chain = validate_hash_chain(rows)
            if rows and not chain["chainValid"]:
                mark_hydration_failed(
                    f"hash_chain_invalid account={self.account_id} errors={chain['errors']}"
                )
                self._chain_valid = False
                self._loaded = True
                return {"ok": False, **chain, "accountId": self.account_id}

            self._events = []
            self._by_idempotency.clear()
            self._by_event_id.clear()
            self.cash = 0.0
            self.margin = 0.0
            self.fees = 0.0
            self.funding = 0.0
            self.realized_pnl = 0.0

            for row in rows:
                self._index(row)
                self._apply_derived(row)

            self._chain_valid = True
            self._loaded = True
            clear_hydration_failed()
            return {
                "ok": True,
                **chain,
                "accountId": self.account_id,
                "cash": self.cash,
                "margin": self.margin,
                "eventsLoaded": len(self._events),
            }

    def _index(self, row: dict[str, Any]) -> None:
        self._events.append(row)
        eid = str(row.get("eventId") or "")
        if eid:
            self._by_event_id[eid] = row
        ik = str(row.get("idempotencyKey") or "")
        if ik:
            self._by_idempotency[ik] = row

    def _apply_derived(self, row: dict[str, Any]) -> None:
        et = str(row.get("eventType") or "")
        amount = float(row.get("amount") or 0.0)
        if et in (EVT_INITIAL_DEPOSIT, EVT_DEPOSIT_LEGACY):
            self.cash += amount
        elif et == EVT_MARGIN_RESERVED:
            self.cash -= amount
            self.margin += amount
        elif et == EVT_MARGIN_RELEASED:
            release = min(amount, self.margin)
            self.margin -= release
            self.cash += release
        elif et == EVT_ORDER_FILLED:
            # Fee may be nested; amount here is optional notional — fees via FEE_CHARGED
            pass
        elif et == EVT_FEE_CHARGED:
            self.fees += amount
            self.cash -= amount
        elif et == EVT_FUNDING_CHARGED:
            self.funding += amount
            self.cash -= amount
        elif et in (EVT_PNL_REALIZED, EVT_PNL_REALISED_LEGACY):
            self.realized_pnl += amount
            self.cash += amount
        elif et == EVT_ADJUSTMENT_VALIDATION_ONLY:
            self.cash += amount

    def ensure_initial_deposit(
        self,
        amount: float = 10_000.0,
        *,
        currency: str = "USDT",
        boot_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Create INITIAL_DEPOSIT only when account has zero durable events."""
        with self._lock:
            if not self._loaded:
                self.load_and_replay()
            if self._events:
                return {
                    "ok": True,
                    "seeded": False,
                    "existingEventId": self._events[0].get("eventId"),
                    "reason": "ledger_not_empty",
                }
            if _HYDRATION_FAILED:
                return {"ok": False, "seeded": False, "reason": "hydration_failed"}
            ik = f"SIM_INITIAL_EQUITY:{self.account_id}:v1"
            return self.append_event(
                event_type=EVT_INITIAL_DEPOSIT,
                amount=amount,
                currency=currency,
                idempotency_key=ik,
                boot_id=boot_id,
                correlation_id=correlation_id,
                payload={"reason": "initial_simulation_capital"},
            )

    def append_event(
        self,
        *,
        event_type: str,
        amount: float,
        idempotency_key: str,
        currency: str = "USDT",
        boot_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        if event_type not in _DURABLE_TYPES:
            return {"ok": False, "error": f"unknown_event_type:{event_type}"}
        if _HYDRATION_FAILED and self.source == SOURCE_PAPER:
            return {"ok": False, "error": "ledger_hydration_failed_blocks_append"}

        with self._lock:
            if not self._loaded:
                self.load_and_replay()
            existing = self._by_idempotency.get(idempotency_key)
            if existing is not None:
                return {
                    "ok": True,
                    "deduped": True,
                    "event": existing,
                    "eventId": existing.get("eventId"),
                }

            seq = (int(self._events[-1]["sequence"]) + 1) if self._events else 1
            prev_hash = (
                str(self._events[-1].get("eventHash"))
                if self._events
                else "GENESIS"
            )
            eid = event_id or str(uuid.uuid4())
            occurred_at = int(time.time() * 1000)
            body: dict[str, Any] = {
                "eventId": eid,
                "event_id": eid,
                "accountId": self.account_id,
                "account_id": self.account_id,
                "sequence": seq,
                "eventType": event_type,
                "entry_type": event_type,
                "amount": float(amount),
                "currency": currency,
                "occurredAt": occurred_at,
                "createdBootId": boot_id,
                "correlationId": correlation_id,
                "causationId": causation_id,
                "idempotencyKey": idempotency_key,
                "previousEventHash": prev_hash if seq > 1 else "GENESIS",
                "source": self.source,
                "schemaVersion": SCHEMA_VERSION,
                "payload": payload or {},
                "researchOnly": True,
                "excludeFromNaturalPaperPnl": self.source == SOURCE_VALIDATION,
            }
            body["eventHash"] = compute_event_hash(body)
            # Persist first — SoT
            try:
                _persist_event(body)
            except Exception as exc:  # noqa: BLE001
                logger.error("[durable_ledger] persist failed: %s", exc)
                return {"ok": False, "error": str(exc)}

            self._index(body)
            self._apply_derived(body)
            return {"ok": True, "deduped": False, "event": body, "eventId": eid}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            chain = validate_hash_chain(list(self._events))
            return {
                "ok": True,
                "researchOnly": True,
                "accountId": self.account_id,
                "source": self.source,
                "cashBalance": self.cash,
                "marginUsed": self.margin,
                "totalFees": self.fees,
                "totalFunding": self.funding,
                "totalRealisedPnl": self.realized_pnl,
                "equity": self.cash + self.margin,
                "eventLogSize": len(self._events),
                "totalEvents": len(self._events),
                "sequenceHead": int(self._events[-1]["sequence"]) if self._events else 0,
                "ledgerHeadHash": chain_head_hash(self._events),
                "ledgerChainValid": chain["chainValid"],
                "eventIds": [e.get("eventId") for e in self._events],
                "hydrationFailed": _HYDRATION_FAILED,
                "generatedAt": int(time.time() * 1000),
            }

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events[-limit:])

    def chain_report(self) -> dict[str, Any]:
        with self._lock:
            return validate_hash_chain(list(self._events))


def get_durable_ledger(
    account_id: str = ACCOUNT_PAPER_DEFAULT,
    *,
    source: str | None = None,
) -> DurableLedgerAccount:
    with _LOCK:
        if account_id not in _ACCOUNTS:
            src = source or (
                SOURCE_VALIDATION
                if account_id.startswith("PERSISTENCE_VALIDATION")
                else SOURCE_PAPER
            )
            acct = DurableLedgerAccount(account_id, source=src)
            acct.load_and_replay()
            # Seed only when empty and not failed.
            if not acct._events and not _HYDRATION_FAILED:
                try:
                    from backend.nexus_research.boot_identity import get_boot_identity

                    boot_id = get_boot_identity().get("bootId")
                except Exception:  # noqa: BLE001
                    boot_id = None
                acct.ensure_initial_deposit(boot_id=boot_id)
            _ACCOUNTS[account_id] = acct
        return _ACCOUNTS[account_id]


def reset_durable_ledger_cache() -> None:
    """Test helper — does not wipe SQLite."""
    with _LOCK:
        _ACCOUNTS.clear()
