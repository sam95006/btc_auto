"""Append-only Shadow Decision Ledger with seal/immutability."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from backend.nexus_shadow_decision_ledger.constants import HARD_BANS, SCHEMA
from backend.nexus_shadow_decision_ledger.contracts import (
    ShadowDecisionContractError,
    ShadowDecisionRecord,
    enforce_public_invariants,
    utc_now,
)
from backend.nexus_shadow_decision_ledger.lifecycle import (
    InvalidShadowTransitionError,
    ShadowDecisionLifecycle,
)


class ShadowLedgerError(RuntimeError):
    """Fail-closed ledger error."""


class ShadowDecisionLedger:
    """In-memory + optional JSONL persistence for Shadow Decisions.

    Never places exchange orders. Sealed records are immutable.
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, ShadowDecisionRecord] = {}
        self._storage_path = storage_path
        self.schema = SCHEMA
        self.actual_ordered_count = 0
        self.actual_filled_count = 0
        self.exchange_write_attempt_count = 0
        self.active_lesson_count = 0
        if storage_path and storage_path.exists():
            self._load(storage_path)

    def _load(self, path: Path) -> None:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            rec = ShadowDecisionRecord(**{k: v for k, v in raw.items() if k in ShadowDecisionRecord.__dataclass_fields__})
            self._records[rec.shadow_decision_id] = rec

    def _persist(self, record: ShadowDecisionRecord) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._storage_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, default=str) + "\n")

    def create(self, record: ShadowDecisionRecord) -> ShadowDecisionRecord:
        with self._lock:
            if record.shadow_decision_id in self._records:
                raise ShadowLedgerError(f"duplicate_id:{record.shadow_decision_id}")
            record.validate_required()
            enforce_public_invariants(record.to_dict())
            self._records[record.shadow_decision_id] = record
            self._persist(record)
            return record

    def get(self, shadow_decision_id: str) -> ShadowDecisionRecord:
        with self._lock:
            if shadow_decision_id not in self._records:
                raise ShadowLedgerError(f"not_found:{shadow_decision_id}")
            return self._records[shadow_decision_id]

    def lifecycle(self, shadow_decision_id: str) -> ShadowDecisionLifecycle:
        return ShadowDecisionLifecycle(self.get(shadow_decision_id))

    def update_fields(
        self,
        shadow_decision_id: str,
        **fields: Any,
    ) -> ShadowDecisionRecord:
        with self._lock:
            rec = self.get(shadow_decision_id)
            if rec.sealed:
                raise ShadowLedgerError("no_rewrite_sealed_record")
            banned = {
                "actual_ordered",
                "actual_filled",
                "exchange_order_id",
                "shadow_decision_id",
                "sealed",
                "content_hash",
            }
            for key, value in fields.items():
                if key in banned:
                    raise ShadowDecisionContractError(f"forbidden_field_mutation:{key}")
                if not hasattr(rec, key):
                    raise ShadowDecisionContractError(f"unknown_field:{key}")
                setattr(rec, key, value)
            rec.updated_at = utc_now()
            rec.actual_ordered = False
            rec.actual_filled = False
            rec.exchange_order_id = None
            rec.validate_required()
            self._persist(rec)
            return rec

    def seal(self, shadow_decision_id: str) -> ShadowDecisionRecord:
        with self._lock:
            rec = self.get(shadow_decision_id)
            if rec.sealed:
                return rec
            if rec.lifecycle_state != "REFLECTED":
                raise ShadowLedgerError(
                    f"seal_requires_REFLECTED:got={rec.lifecycle_state}"
                )
            rec.actual_ordered = False
            rec.actual_filled = False
            rec.exchange_order_id = None
            rec.validate_required()
            rec.sealed = True
            rec.updated_at = utc_now()
            # Hash after seal flag is set; excludes content_hash / updated_at.
            rec.content_hash = rec.compute_hash()
            self._persist(rec)
            return rec

    def assert_immutable(self, shadow_decision_id: str) -> None:
        rec = self.get(shadow_decision_id)
        if not rec.sealed or not rec.content_hash:
            raise ShadowLedgerError("record_not_sealed")
        current = rec.compute_hash()
        if current != rec.content_hash:
            raise ShadowLedgerError("sealed_content_hash_mismatch")

    def attempt_exchange_order(self, *_args: Any, **_kwargs: Any) -> None:
        """Hard ban: ledger never places orders.

        exchange_write_attempt_count stays 0 — the call is refused before any write path.
        """
        raise ShadowLedgerError("no_exchange_write:" + ",".join(HARD_BANS[:3]))

    def attempt_set_actual_ordered(self, shadow_decision_id: str, value: bool = True) -> None:
        """Hard ban: cannot mark Shadow Decisions as actually ordered."""
        _ = (shadow_decision_id, value)
        raise ShadowDecisionContractError("no_actual_ordered")

    def list_records(self) -> list[ShadowDecisionRecord]:
        with self._lock:
            return list(self._records.values())

    def counts(self) -> dict[str, int]:
        with self._lock:
            return {
                "shadow_decision_count": len(self._records),
                "sealed_count": sum(1 for r in self._records.values() if r.sealed),
                "virtual_research_position_count": sum(
                    1 for r in self._records.values() if r.virtual_research_position
                ),
                "actual_ordered_count": self.actual_ordered_count,
                "actual_filled_count": self.actual_filled_count,
                "exchange_write_attempt_count": self.exchange_write_attempt_count,
                "active_lesson_count": self.active_lesson_count,
                "lesson_candidate_ref_count": sum(
                    len(r.lesson_candidate_refs) for r in self._records.values()
                ),
            }

    def refuse_invalid_transition(self, shadow_decision_id: str, next_state: str) -> None:
        lc = self.lifecycle(shadow_decision_id)
        try:
            lc.transition(next_state, reason="refuse_probe", idempotency_key=f"refuse:{next_state}")
        except InvalidShadowTransitionError:
            return
        raise ShadowLedgerError(f"expected_invalid_transition_to_fail:{next_state}")
