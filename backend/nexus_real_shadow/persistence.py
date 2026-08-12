"""Append-only persistence adapters for Wave 5 real public shadow runtime."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


def checksum_record(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class PersistenceAdapter(Protocol):
    def append(self, stream: str, record: dict[str, Any]) -> str: ...
    def read_all(self, stream: str) -> list[dict[str, Any]]: ...


@dataclass
class FilePersistenceAdapter:
    root: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, stream: str) -> Path:
        safe = stream.replace("/", "_")
        return self.root / f"{safe}.jsonl"

    def append(self, stream: str, record: dict[str, Any]) -> str:
        rec = dict(record)
        rec["checksum"] = checksum_record(rec)
        path = self._path(stream)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec["checksum"]

    def read_all(self, stream: str) -> list[dict[str, Any]]:
        path = self._path(stream)
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows


@dataclass
class SQLitePersistenceAdapter:
    db_path: Path

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shadow_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stream TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    created_at REAL DEFAULT (strftime('%s','now'))
                )
                """
            )

    def append(self, stream: str, record: dict[str, Any]) -> str:
        rec = dict(record)
        cs = checksum_record(rec)
        rec["checksum"] = cs
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO shadow_records (stream, payload, checksum) VALUES (?, ?, ?)",
                (stream, json.dumps(rec, sort_keys=True), cs),
            )
        return cs

    def read_all(self, stream: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT payload FROM shadow_records WHERE stream = ? ORDER BY id ASC",
                (stream,),
            )
            return [json.loads(row[0]) for row in cur.fetchall()]


@dataclass
class InMemoryPersistenceAdapter:
    """In-memory append-only store for deterministic CI."""

    _streams: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def append(self, stream: str, record: dict[str, Any]) -> str:
        rec = dict(record)
        cs = checksum_record(rec)
        rec["checksum"] = cs
        self._streams.setdefault(stream, []).append(rec)
        return cs

    def read_all(self, stream: str) -> list[dict[str, Any]]:
        return list(self._streams.get(stream) or [])


class PostgresPersistenceStub:
    """Stub adapter — documents interface without requiring Postgres in CI."""

    def append(self, stream: str, record: dict[str, Any]) -> str:
        rec = dict(record)
        rec["checksum"] = checksum_record(rec)
        rec["_postgres_stub"] = True
        rec["_stream"] = stream
        return rec["checksum"]

    def read_all(self, stream: str) -> list[dict[str, Any]]:
        return []
