"""Immutable promotion record for V16-F Lesson Validation Firewall."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.nexus_lesson_validation_firewall.bans import refuse_immutable_record_rewrite
from backend.nexus_lesson_validation_firewall.constants import SCHEMA_ID


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class ImmutablePromotionRecordStore:
    """Append-only promotion records. Rewrites fail closed."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._chain: list[str] = []

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(record)
        record_id = str(payload.get("record_id") or "")
        if not record_id:
            raise ValueError("record_id_required")
        if record_id in self._records:
            refusal = refuse_immutable_record_rewrite(record_id)
            return {
                "allowed": False,
                "stored": False,
                "record_id": record_id,
                "refusal": refusal,
                "fail_closed": True,
            }
        prev = self._chain[-1] if self._chain else None
        body = {
            k: v
            for k, v in payload.items()
            if k not in {"record_checksum", "prev_checksum", "schema"}
        }
        checksum = _sha({"prev": prev, "body": body})
        sealed = {
            **body,
            "schema": SCHEMA_ID,
            "prev_checksum": prev,
            "record_checksum": checksum,
            "sealed_at": _utc(),
            "immutable": True,
        }
        self._records[record_id] = sealed
        self._chain.append(checksum)
        return {"allowed": True, "stored": True, "record": deepcopy(sealed)}

    def attempt_rewrite(self, record_id: str, mutation: dict[str, Any]) -> dict[str, Any]:
        if record_id not in self._records:
            return {
                "allowed": False,
                "stored": False,
                "record_id": record_id,
                "reason": "UNKNOWN_RECORD",
                "fail_closed": True,
            }
        refusal = refuse_immutable_record_rewrite(record_id)
        # Prove original unchanged.
        original = deepcopy(self._records[record_id])
        _ = mutation  # intentionally unused — never applied
        still = self._records[record_id]
        return {
            "allowed": False,
            "stored": False,
            "record_id": record_id,
            "refusal": refusal,
            "original_checksum": original.get("record_checksum"),
            "current_checksum": still.get("record_checksum"),
            "unchanged": original == still,
            "fail_closed": True,
        }

    def get(self, record_id: str) -> dict[str, Any] | None:
        rec = self._records.get(record_id)
        return deepcopy(rec) if rec is not None else None

    def verify_chain(self) -> dict[str, Any]:
        prev = None
        for checksum in self._chain:
            match = next(
                (r for r in self._records.values() if r.get("record_checksum") == checksum),
                None,
            )
            if match is None:
                return {"ok": False, "reason": "MISSING_RECORD_FOR_CHAIN"}
            if match.get("prev_checksum") != prev:
                return {"ok": False, "reason": "CHAIN_BREAK", "checksum": checksum}
            body = {
                k: v
                for k, v in match.items()
                if k
                not in {
                    "record_checksum",
                    "prev_checksum",
                    "schema",
                    "sealed_at",
                    "immutable",
                }
            }
            expected = _sha({"prev": prev, "body": body})
            if expected != checksum:
                return {"ok": False, "reason": "CHECKSUM_MISMATCH", "checksum": checksum}
            prev = checksum
        return {"ok": True, "length": len(self._chain)}

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_count": len(self._records),
            "chain_length": len(self._chain),
            "chain": list(self._chain),
            "records": {k: deepcopy(v) for k, v in self._records.items()},
            "verify": self.verify_chain(),
        }
