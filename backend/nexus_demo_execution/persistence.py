"""Append-only sqlite persistence for demo execution validation."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STREAMS = frozenset(
    {
        "intents",
        "orders",
        "positions",
        "outcomes",
        "reflections",
        "epochs",
        "snapshots",
        "dry_run_intents",
        "protection_checks",
        "gate_evidence",
        "smoke_sessions",
        "session_checkpoints",
        "decision_deltas",
        "cost_gates",
        "session_summaries",
        "universe_scans",
        "bounded_candidates",
        "session_mistake_telemetry",
        "certified_risk",
        "durable_lessons",
    }
)


def checksum_record(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass
class DemoExecutionPersistence:
    """SQLite append-only store — no updates or deletes."""

    db_path: Path
    _initialized: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS demo_execution_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stream TEXT NOT NULL,
                    account_epoch TEXT,
                    payload TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    created_at REAL DEFAULT (strftime('%s','now'))
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stream_epoch ON demo_execution_records(stream, account_epoch)"
            )
        self._initialized = True

    def append(
        self,
        stream: str,
        record: dict[str, Any],
        *,
        account_epoch: str | None = None,
    ) -> str:
        if stream not in STREAMS:
            raise ValueError(f"unknown_stream:{stream}")
        rec = dict(record)
        cs = checksum_record(rec)
        rec["checksum"] = cs
        if account_epoch:
            rec["account_epoch"] = account_epoch
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO demo_execution_records (stream, account_epoch, payload, checksum)
                VALUES (?, ?, ?, ?)
                """,
                (stream, account_epoch, json.dumps(rec, sort_keys=True), cs),
            )
        return cs

    def read_all(
        self,
        stream: str,
        *,
        account_epoch: str | None = None,
        from_id: int | None = None,
        to_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT id, payload FROM demo_execution_records WHERE stream = ?"
        params: list[Any] = [stream]
        if account_epoch is not None:
            query += " AND account_epoch = ?"
            params.append(account_epoch)
        if from_id is not None:
            query += " AND id >= ?"
            params.append(from_id)
        if to_id is not None:
            query += " AND id <= ?"
            params.append(to_id)
        query += " ORDER BY id ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
            if offset:
                query += " OFFSET ?"
                params.append(int(offset))
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(query, params)
            rows = []
            for row_id, payload in cur.fetchall():
                rec = json.loads(payload)
                rec["_record_id"] = row_id
                rows.append(rec)
            return rows

    def count(self, stream: str, *, account_epoch: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM demo_execution_records WHERE stream = ?"
        params: list[Any] = [stream]
        if account_epoch is not None:
            query += " AND account_epoch = ?"
            params.append(account_epoch)
        with sqlite3.connect(self.db_path) as conn:
            return int(conn.execute(query, params).fetchone()[0])

    def summary(self) -> dict[str, Any]:
        counts = {s: self.count(s) for s in sorted(STREAMS)}
        return {"db_path": str(self.db_path), "stream_counts": counts}
