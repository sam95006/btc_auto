"""Persistence store interfaces and adapters."""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generic, TypeVar

from backend.nexus_global_shadow.contracts import EvidenceEnvelope

T = TypeVar("T")


class EvidenceStore(ABC):
    @abstractmethod
    def append(self, record: dict[str, Any]) -> str: ...

    @abstractmethod
    def get(self, record_id: str) -> dict[str, Any] | None: ...


class UniverseStore(EvidenceStore):
    pass


class CandidateStore(EvidenceStore):
    pass


class ShadowPositionStore(EvidenceStore):
    pass


class InMemoryEvidenceStore(EvidenceStore):
    """Append-only in-memory store with idempotent keys."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def append(self, record: dict[str, Any]) -> str:
        rid = str(record.get("record_id") or record.get("candidate_id") or "")
        if rid and rid in self._records:
            return rid
        if isinstance(record, EvidenceEnvelope):
            record = record.finalize().to_dict()
        elif "checksum" not in record or not record.get("checksum"):
            env = EvidenceEnvelope(**{k: v for k, v in record.items() if k in EvidenceEnvelope.__dataclass_fields__})
            record = env.finalize().to_dict()
        self._seq += 1
        record["sequence_number"] = self._seq
        rid = str(record.get("record_id") or f"rec_{self._seq}")
        record["record_id"] = rid
        self._records[rid] = record
        return rid

    def get(self, record_id: str) -> dict[str, Any] | None:
        return self._records.get(record_id)

    def all_records(self) -> list[dict[str, Any]]:
        return list(self._records.values())


class FileEvidenceStore(InMemoryEvidenceStore):
    """File-backed append-only evidence."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self._records[rec["record_id"]] = rec

    def append(self, record: dict[str, Any]) -> str:
        rid = super().append(record)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(self._records[rid], sort_keys=True) + "\n")
        return rid


class PostgresEvidenceStoreStub(EvidenceStore):
    """Stub for future Zeabur Postgres — not connected."""

    def __init__(self, dsn: str = "") -> None:
        self.dsn = dsn
        self.connected = False

    def append(self, record: dict[str, Any]) -> str:
        raise NotImplementedError("postgres_stub_not_connected")

    def get(self, record_id: str) -> dict[str, Any] | None:
        raise NotImplementedError("postgres_stub_not_connected")


def verify_checksum(record: dict[str, Any]) -> bool:
    stored = record.get("checksum")
    if not stored:
        return False
    env = EvidenceEnvelope(**{k: v for k, v in record.items() if k in EvidenceEnvelope.__dataclass_fields__})
    env.checksum = ""
    finalized = env.finalize()
    return finalized.checksum == stored
