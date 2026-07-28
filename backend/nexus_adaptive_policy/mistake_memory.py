"""Mistake memory store and similarity index."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_adaptive_policy.failure_taxonomy import FailureClassification, FailureType


@dataclass(frozen=True)
class FailureSignature:
    failure_type: str
    symbol: str
    strategy_id: str
    regime: str = "UNKNOWN"

    def digest(self) -> str:
        raw = json.dumps(
            {
                "failure_type": self.failure_type,
                "symbol": self.symbol,
                "strategy_id": self.strategy_id,
                "regime": self.regime,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class MistakeRecord:
    record_id: str
    case_id: str
    signature: FailureSignature
    classification: FailureClassification
    occurrence_count: int = 1
    last_seen_ms: int = 0


class MistakeSimilarityIndex:
    """In-memory index keyed by failure signature digest."""

    def __init__(self) -> None:
        self._by_digest: dict[str, list[str]] = {}
        self._records: dict[str, MistakeRecord] = {}

    def add(self, record: MistakeRecord) -> None:
        self._records[record.record_id] = record
        digest = record.signature.digest()
        self._by_digest.setdefault(digest, []).append(record.record_id)

    def find_similar(self, signature: FailureSignature, limit: int = 5) -> list[MistakeRecord]:
        ids = self._by_digest.get(signature.digest(), [])
        return [self._records[i] for i in ids[:limit] if i in self._records]

    def count_by_type(self, failure_type: FailureType) -> int:
        return sum(
            1
            for r in self._records.values()
            if r.classification.failure_type == failure_type
        )


class MistakeMemoryStore:
    """Append-only mistake memory with similarity lookup."""

    def __init__(self) -> None:
        self.index = MistakeSimilarityIndex()
        self._seq = 0

    def remember(
        self,
        case_id: str,
        classification: FailureClassification,
        *,
        symbol: str,
        strategy_id: str,
        regime: str = "UNKNOWN",
        now_ms: int = 0,
    ) -> MistakeRecord:
        sig = FailureSignature(
            failure_type=classification.failure_type.value,
            symbol=symbol,
            strategy_id=strategy_id,
            regime=regime,
        )
        similar = self.index.find_similar(sig)
        if similar:
            rec = similar[0]
            rec.occurrence_count += 1
            rec.last_seen_ms = now_ms
            return rec
        self._seq += 1
        record = MistakeRecord(
            record_id=f"mistake_{self._seq:06d}",
            case_id=case_id,
            signature=sig,
            classification=classification,
            last_seen_ms=now_ms,
        )
        self.index.add(record)
        return record

    def list_records(self) -> list[MistakeRecord]:
        return list(self.index._records.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": len(self.index._records),
            "records": [
                {
                    "record_id": r.record_id,
                    "case_id": r.case_id,
                    "occurrence_count": r.occurrence_count,
                    "signature": {
                        "failure_type": r.signature.failure_type,
                        "symbol": r.signature.symbol,
                        "strategy_id": r.signature.strategy_id,
                        "regime": r.signature.regime,
                    },
                    "classification": r.classification.to_dict(),
                }
                for r in self.index._records.values()
            ],
        }
