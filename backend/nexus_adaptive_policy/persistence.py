"""Append-only persistence with checksum verification."""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def compute_checksum(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class PersistedRecord:
    record_type: str
    payload: dict[str, Any]
    checksum: str = ""
    seq: int = 0

    def seal(self) -> "PersistedRecord":
        self.checksum = compute_checksum({"record_type": self.record_type, "payload": self.payload, "seq": self.seq})
        return self

    def verify(self) -> bool:
        expected = compute_checksum({"record_type": self.record_type, "payload": self.payload, "seq": self.seq})
        return self.checksum == expected


class AdaptivePolicyStore(ABC):
    @abstractmethod
    def append(self, record_type: str, payload: dict[str, Any]) -> PersistedRecord: ...

    @abstractmethod
    def list_records(self, record_type: str | None = None) -> list[PersistedRecord]: ...


class InMemoryAdaptivePolicyStore(AdaptivePolicyStore):
    def __init__(self) -> None:
        self._records: list[PersistedRecord] = []
        self._seq = 0

    def append(self, record_type: str, payload: dict[str, Any]) -> PersistedRecord:
        self._seq += 1
        rec = PersistedRecord(record_type=record_type, payload=dict(payload), seq=self._seq).seal()
        self._records.append(rec)
        return rec

    def list_records(self, record_type: str | None = None) -> list[PersistedRecord]:
        if record_type is None:
            return list(self._records)
        return [r for r in self._records if r.record_type == record_type]


class FileAdaptivePolicyStore(AdaptivePolicyStore):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory = InMemoryAdaptivePolicyStore()
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rec = PersistedRecord(
                record_type=row["record_type"],
                payload=row["payload"],
                checksum=row["checksum"],
                seq=row["seq"],
            )
            if rec.verify():
                self._memory._records.append(rec)
                self._memory._seq = max(self._memory._seq, rec.seq)

    def append(self, record_type: str, payload: dict[str, Any]) -> PersistedRecord:
        rec = self._memory.append(record_type, payload)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "record_type": rec.record_type,
                        "payload": rec.payload,
                        "checksum": rec.checksum,
                        "seq": rec.seq,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
        return rec

    def list_records(self, record_type: str | None = None) -> list[PersistedRecord]:
        return self._memory.list_records(record_type)


class PostgresAdaptivePolicyStoreStub(AdaptivePolicyStore):
    """Stub — records intent only; no live DB connection in shadow mode."""

    def __init__(self, dsn: str = "") -> None:
        self.dsn = dsn
        self._memory = InMemoryAdaptivePolicyStore()
        self.connected = False

    def append(self, record_type: str, payload: dict[str, Any]) -> PersistedRecord:
        return self._memory.append(record_type, payload)

    def list_records(self, record_type: str | None = None) -> list[PersistedRecord]:
        return self._memory.list_records(record_type)

    def connect(self) -> bool:
        self.connected = bool(self.dsn)
        return self.connected
