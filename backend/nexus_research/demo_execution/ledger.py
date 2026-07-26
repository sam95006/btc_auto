"""Demo order execution — execution ledger and audit trail.

Secret-safe: no API keys, secrets, or credentials in logs.
Audit trail is append-only with hash chain for integrity.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False

_SECRET_PATTERNS = frozenset({
    "api_key", "apiKey", "api_secret", "apiSecret",
    "secret", "password", "token", "credential",
    "private_key", "privateKey",
})


def _sanitize(data: dict[str, Any]) -> dict[str, Any]:
    """Strip any accidental secret-like keys from audit data."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if any(pat in k.lower() for pat in _SECRET_PATTERNS):
            out[k] = "***REDACTED***"
        elif isinstance(v, dict):
            out[k] = _sanitize(v)
        else:
            out[k] = v
    return out


@dataclass
class LedgerEntry:
    entry_id: str
    order_id: str
    event: str  # INTENT_CREATED | PREFLIGHT | AUTHORIZED | STATE_CHANGE | CLOSE | RECONCILE
    state: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    order_sent: bool = field(default=False, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entryId": self.entry_id,
            "orderId": self.order_id,
            "event": self.event,
            "state": self.state,
            "data": _sanitize(self.data),
            "timestampMs": self.timestamp_ms,
            "orderSent": False,
        }


class DemoExecutionLedger:
    """Append-only ledger of all execution events."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._counter: int = 0

    def append(
        self,
        order_id: str,
        event: str,
        state: str,
        data: dict[str, Any] | None = None,
    ) -> LedgerEntry:
        self._counter += 1
        entry = LedgerEntry(
            entry_id=f"LE-{self._counter:06d}",
            order_id=order_id,
            event=event,
            state=state,
            data=_sanitize(data or {}),
        )
        self._entries.append(entry)
        return entry

    @property
    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)

    def entries_for_order(self, order_id: str) -> list[LedgerEntry]:
        return [e for e in self._entries if e.order_id == order_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "entryCount": len(self._entries),
            "entries": [e.to_dict() for e in self._entries],
            "orderSent": False,
        }


@dataclass
class AuditRecord:
    """Single audit record with hash chain link."""

    seq: int
    event: str
    order_id: str
    detail: dict[str, Any]
    timestamp_ms: int
    prev_hash: str
    record_hash: str = ""

    def __post_init__(self) -> None:
        if not self.record_hash:
            blob = json.dumps(
                {
                    "seq": self.seq,
                    "event": self.event,
                    "orderId": self.order_id,
                    "detail": self.detail,
                    "timestampMs": self.timestamp_ms,
                    "prevHash": self.prev_hash,
                },
                sort_keys=True,
            )
            self.record_hash = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "event": self.event,
            "orderId": self.order_id,
            "detail": _sanitize(self.detail),
            "timestampMs": self.timestamp_ms,
            "prevHash": self.prev_hash[:16],
            "recordHash": self.record_hash[:16],
        }


class DemoOrderAuditTrail:
    """Secret-safe, append-only audit trail with hash chain integrity."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._prev_hash: str = hashlib.sha256(b"genesis").hexdigest()

    def record(
        self,
        event: str,
        order_id: str,
        detail: dict[str, Any] | None = None,
    ) -> AuditRecord:
        sanitized = _sanitize(detail or {})
        rec = AuditRecord(
            seq=len(self._records) + 1,
            event=event,
            order_id=order_id,
            detail=sanitized,
            timestamp_ms=int(time.time() * 1000),
            prev_hash=self._prev_hash,
        )
        self._prev_hash = rec.record_hash
        self._records.append(rec)
        return rec

    def verify_chain(self) -> bool:
        """Verify hash chain integrity."""
        expected = hashlib.sha256(b"genesis").hexdigest()
        for rec in self._records:
            if rec.prev_hash != expected:
                return False
            expected = rec.record_hash
        return True

    @property
    def records(self) -> list[AuditRecord]:
        return list(self._records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recordCount": len(self._records),
            "chainValid": self.verify_chain(),
            "records": [r.to_dict() for r in self._records],
            "orderSent": False,
        }
