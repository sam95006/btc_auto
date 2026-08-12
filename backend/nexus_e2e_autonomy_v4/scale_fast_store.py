"""In-memory durability adapters for V15-K scale loop.

Focused probes still exercise real durable checkpoint/ledger/recovery paths.
The 100k closed-loop volume uses memory adapters so NTFS does not collapse under
per-stage checkpoint fan-out while preserving in-process correctness counters.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from backend.nexus_decision.checkpoint import sanitize_checkpoint_payload


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ScaleMemoryCheckpointStore:
    """Latest-only in-memory checkpoint store (no per-seq disk files)."""

    def __init__(self) -> None:
        self._seq = 0
        self._latest: dict[str, dict[str, Any]] = {}

    def save(self, decision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        cleaned = sanitize_checkpoint_payload(dict(payload))
        cleaned["checkpoint_seq"] = self._seq
        cleaned["checkpoint_at"] = _utc()
        cleaned["decision_id"] = decision_id
        text = json.dumps(cleaned, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        digest = _sha(text)
        cleaned["checkpoint_sha256"] = digest
        self._latest[decision_id] = cleaned
        return {
            "checkpoint_id": f"{decision_id}:{self._seq:04d}",
            "path": f"memory://{decision_id}",
            "sha256": digest,
            "seq": self._seq,
            "created_at": cleaned["checkpoint_at"],
        }

    def load_latest(self, decision_id: str) -> dict[str, Any] | None:
        return self._latest.get(decision_id)

    def verify_latest(self, decision_id: str) -> bool:
        payload = self.load_latest(decision_id)
        if not payload:
            return False
        stored = payload.get("checkpoint_sha256")
        if not stored:
            return False
        check = dict(payload)
        check.pop("checkpoint_sha256", None)
        text = json.dumps(check, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        return _sha(text) == stored


class ScaleMemoryLedgerLink:
    """In-memory decision ledger append matching DecisionLedgerLink.append contract."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._seq = 0
        self._idempotency: dict[str, str] = {}

    @property
    def sequence_number(self) -> int:
        return self._seq

    def append(
        self,
        *,
        decision_id: str,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        source: str = "nexus_e2e_autonomy_v4.scale_fast_store",
    ) -> dict[str, Any]:
        if idempotency_key in self._idempotency:
            return {
                "status": "DUPLICATE_IGNORED",
                "event_id": self._idempotency[idempotency_key],
                "duplicate": True,
                "sequence_number": None,
            }
        # Mirror durable ledger secret refusal (fail-closed, no silent accept).
        flat = json.dumps(payload, sort_keys=True, default=str).lower()
        banned = ("api_key", "api_secret", "password", "private_key", "authorization")
        if any(b in flat for b in banned):
            raise ValueError("ledger_payload_contains_forbidden_secret_fields")
        self._seq += 1
        event_id = _sha(f"{decision_id}:{event_type}:{idempotency_key}:{self._seq}")[:32]
        self._idempotency[idempotency_key] = event_id
        row = {
            "sequence_number": self._seq,
            "event_id": event_id,
            "decision_id": decision_id,
            "event_type": event_type,
            "payload": payload,
            "source": source,
            "at": _utc(),
        }
        self._events.append(row)
        return {
            "status": "APPENDED",
            "event_id": event_id,
            "duplicate": False,
            "sequence_number": self._seq,
        }


__all__ = [
    "ScaleMemoryCheckpointStore",
    "ScaleMemoryLedgerLink",
]
