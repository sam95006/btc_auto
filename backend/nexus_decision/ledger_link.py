"""Append-only Decision Lifecycle ledger linkage (Founder-private, local only).

Links Decision Object transitions to durable ledger events without secrets.
Uses PrivateEventLedger when available; otherwise JSONL fallback under root.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "nexus_decision_ledger_link_v11"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DecisionLedgerLink:
    """Hash-chained append-only decision event log with idempotency."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "decision_lifecycle_ledger.jsonl"
        self._lock = threading.RLock()
        self._prev_hash = "0" * 64
        self._seq = 0
        self._idempotency: dict[str, str] = {}
        self._bootstrap()

    def _bootstrap(self) -> None:
        if not self.path.exists():
            return
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                evt = json.loads(line)
                self._seq = max(self._seq, int(evt.get("sequence_number") or 0))
                self._prev_hash = str(evt.get("event_hash") or self._prev_hash)
                key = evt.get("idempotency_key")
                if key:
                    self._idempotency[str(key)] = str(evt.get("event_id"))
        except (OSError, json.JSONDecodeError, ValueError):
            # Fail closed: refuse to continue on corrupt ledger.
            raise RuntimeError("decision_ledger_corrupt_or_unreadable")

    def append(
        self,
        *,
        decision_id: str,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        source: str = "nexus_decision.orchestrator",
    ) -> dict[str, Any]:
        with self._lock:
            if idempotency_key in self._idempotency:
                return {
                    "status": "DUPLICATE_IGNORED",
                    "event_id": self._idempotency[idempotency_key],
                    "duplicate": True,
                    "sequence_number": None,
                }
            # Refuse secret-like keys in payload.
            flat = json.dumps(payload, sort_keys=True, default=str).lower()
            banned = ("api_key", "api_secret", "password", "private_key", "authorization")
            if any(b in flat for b in banned):
                raise ValueError("ledger_payload_contains_forbidden_secret_fields")

            self._seq += 1
            payload_json = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
            payload_hash = _sha(payload_json)
            created_at = _utc()
            event_id = _sha(f"{decision_id}:{event_type}:{idempotency_key}:{self._seq}")[:32]
            body = {
                "schema": SCHEMA,
                "sequence_number": self._seq,
                "event_id": event_id,
                "aggregate_id": decision_id,
                "aggregate_type": "DECISION",
                "event_type": event_type,
                "previous_event_hash": self._prev_hash,
                "created_at": created_at,
                "source": source,
                "idempotency_key": idempotency_key,
                "payload_hash": payload_hash,
                "payload_redaction_status": "REDACTED_SAFE",
                "payload": payload,
            }
            event_hash = _sha(
                json.dumps(
                    {k: body[k] for k in sorted(body) if k != "event_hash"},
                    sort_keys=True,
                    default=str,
                    separators=(",", ":"),
                )
            )
            body["event_hash"] = event_hash
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(body, sort_keys=True, default=str) + "\n")
                fh.flush()
            self._prev_hash = event_hash
            self._idempotency[idempotency_key] = event_id
            return {
                "status": "APPENDED",
                "event_id": event_id,
                "duplicate": False,
                "sequence_number": self._seq,
                "event_hash": event_hash,
                "payload_hash": payload_hash,
            }

    def events_for(self, decision_id: str) -> list[dict[str, Any]]:
        with self._lock:
            if not self.path.exists():
                return []
            out: list[dict[str, Any]] = []
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                evt = json.loads(line)
                if evt.get("aggregate_id") == decision_id:
                    out.append(evt)
            return out

    @property
    def sequence_number(self) -> int:
        with self._lock:
            return self._seq
