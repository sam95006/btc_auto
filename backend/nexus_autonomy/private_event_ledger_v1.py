"""NEXUS Private Event Ledger V1 — append-only hash-chained durable events.

No secrets / raw prompts / raw provider responses.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AGGREGATE_TYPES = (
    "CANDIDATE",
    "DECISION",
    "ORDER_INTENT",
    "SIMULATED_POSITION",
    "TRADE_OUTCOME",
    "REFLECTION",
    "LESSON",
    "PROVIDER_REQUEST",
    "DATA_CAPTURE_SESSION",
    "SNAPSHOT",
)

SCHEMA_VERSION = "private_event_ledger_v1"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class AppendResult:
    status: str
    event_id: str | None
    sequence_number: int | None
    duplicate: bool = False


class PrivateEventLedger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _migrate(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ledger_meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              sequence_number INTEGER PRIMARY KEY AUTOINCREMENT,
              event_id TEXT NOT NULL UNIQUE,
              aggregate_id TEXT NOT NULL,
              aggregate_type TEXT NOT NULL,
              event_type TEXT NOT NULL,
              previous_event_hash TEXT NOT NULL,
              event_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              source TEXT NOT NULL,
              schema_version TEXT NOT NULL,
              idempotency_key TEXT,
              payload_hash TEXT NOT NULL,
              payload_redaction_status TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idempotency
              ON events(idempotency_key) WHERE idempotency_key IS NOT NULL;
            """
        )
        cur = self._conn.execute("SELECT value FROM ledger_meta WHERE key='schema_version'")
        row = cur.fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO ledger_meta(key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )
            self._conn.execute(
                "INSERT INTO ledger_meta(key, value) VALUES ('genesis_hash', ?)",
                ("0" * 64,),
            )
        self._conn.commit()

    def _last_hash(self) -> str:
        cur = self._conn.execute("SELECT event_hash FROM events ORDER BY sequence_number DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            return row["event_hash"]
        cur = self._conn.execute("SELECT value FROM ledger_meta WHERE key='genesis_hash'")
        return cur.fetchone()["value"]

    def append(
        self,
        *,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        source: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        payload_redaction_status: str = "REDACTED_SAFE",
    ) -> AppendResult:
        if aggregate_type not in AGGREGATE_TYPES:
            raise ValueError(f"invalid_aggregate_type:{aggregate_type}")
        # Refuse secret-like keys
        banned = {"api_key", "secret", "password", "authorization", "private_key"}
        flat = json.dumps(payload, sort_keys=True, default=str).lower()
        if any(b in flat for b in banned):
            raise ValueError("payload_contains_forbidden_secret_fields")

        payload_json = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        payload_hash = _sha(payload_json)

        with self._lock:
            if idempotency_key:
                cur = self._conn.execute(
                    "SELECT event_id, sequence_number FROM events WHERE idempotency_key=?",
                    (idempotency_key,),
                )
                existing = cur.fetchone()
                if existing:
                    return AppendResult(
                        status="DUPLICATE_IGNORED",
                        event_id=existing["event_id"],
                        sequence_number=existing["sequence_number"],
                        duplicate=True,
                    )

            prev = self._last_hash()
            created_at = _utc()
            event_id = _sha(f"{aggregate_id}|{event_type}|{created_at}|{payload_hash}|{time.time_ns()}")[:32]
            # sequence assigned by AUTOINCREMENT; hash uses provisional next
            cur = self._conn.execute("SELECT IFNULL(MAX(sequence_number),0)+1 AS nxt FROM events")
            seq = int(cur.fetchone()["nxt"])
            material = "|".join(
                [
                    event_id,
                    aggregate_id,
                    aggregate_type,
                    event_type,
                    str(seq),
                    prev,
                    created_at,
                    source,
                    SCHEMA_VERSION,
                    idempotency_key or "",
                    payload_hash,
                    payload_redaction_status,
                ]
            )
            event_hash = _sha(material)
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(
                    """
                    INSERT INTO events(
                      sequence_number, event_id, aggregate_id, aggregate_type, event_type,
                      previous_event_hash, event_hash, created_at, source,
                      schema_version, idempotency_key, payload_hash,
                      payload_redaction_status, payload_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        seq,
                        event_id,
                        aggregate_id,
                        aggregate_type,
                        event_type,
                        prev,
                        event_hash,
                        created_at,
                        source,
                        SCHEMA_VERSION,
                        idempotency_key,
                        payload_hash,
                        payload_redaction_status,
                        payload_json,
                    ),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return AppendResult(status="APPENDED", event_id=event_id, sequence_number=seq, duplicate=False)

    def append_many_scale(self, items: list[dict[str, Any]], *, commit_every: int = 1000) -> int:
        """High-throughput append for scale validation only. Still hash-chained and idempotent-keyed."""
        n = 0
        with self._lock:
            prev = self._last_hash()
            cur = self._conn.execute("SELECT IFNULL(MAX(sequence_number),0) AS m FROM events")
            seq = int(cur.fetchone()["m"])
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for item in items:
                    seq += 1
                    payload_json = json.dumps(item["payload"], sort_keys=True, default=str, separators=(",", ":"))
                    payload_hash = _sha(payload_json)
                    created_at = _utc()
                    idem = item.get("idempotency_key")
                    event_id = _sha(f"{item['aggregate_id']}|{item['event_type']}|{created_at}|{payload_hash}|{seq}")[:32]
                    material = "|".join(
                        [
                            event_id,
                            item["aggregate_id"],
                            item["aggregate_type"],
                            item["event_type"],
                            str(seq),
                            prev,
                            created_at,
                            item.get("source") or "scale",
                            SCHEMA_VERSION,
                            idem or "",
                            payload_hash,
                            item.get("payload_redaction_status") or "REDACTED_SAFE",
                        ]
                    )
                    event_hash = _sha(material)
                    self._conn.execute(
                        """
                        INSERT INTO events(
                          sequence_number, event_id, aggregate_id, aggregate_type, event_type,
                          previous_event_hash, event_hash, created_at, source,
                          schema_version, idempotency_key, payload_hash,
                          payload_redaction_status, payload_json
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            seq,
                            event_id,
                            item["aggregate_id"],
                            item["aggregate_type"],
                            item["event_type"],
                            prev,
                            event_hash,
                            created_at,
                            item.get("source") or "scale",
                            SCHEMA_VERSION,
                            idem,
                            payload_hash,
                            item.get("payload_redaction_status") or "REDACTED_SAFE",
                            payload_json,
                        ),
                    )
                    prev = event_hash
                    n += 1
                    if n % commit_every == 0:
                        self._conn.commit()
                        self._conn.execute("BEGIN IMMEDIATE")
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return n

    def event_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"])

    def verify_hash_chain(self) -> dict[str, Any]:
        rows = self._conn.execute(
            "SELECT sequence_number, previous_event_hash, event_hash, event_id, aggregate_id, "
            "aggregate_type, event_type, created_at, source, schema_version, idempotency_key, "
            "payload_hash, payload_redaction_status FROM events ORDER BY sequence_number ASC"
        ).fetchall()
        prev = self._conn.execute("SELECT value FROM ledger_meta WHERE key='genesis_hash'").fetchone()["value"]
        for row in rows:
            material = "|".join(
                [
                    row["event_id"],
                    row["aggregate_id"],
                    row["aggregate_type"],
                    row["event_type"],
                    str(row["sequence_number"]),
                    row["previous_event_hash"],
                    row["created_at"],
                    row["source"],
                    row["schema_version"],
                    row["idempotency_key"] or "",
                    row["payload_hash"],
                    row["payload_redaction_status"],
                ]
            )
            expected = _sha(material)
            if row["previous_event_hash"] != prev or row["event_hash"] != expected:
                return {
                    "ledger_hash_chain_status": "CORRUPTION_DETECTED",
                    "broken_at_sequence": row["sequence_number"],
                }
            prev = row["event_hash"]
        return {"ledger_hash_chain_status": "PASS", "event_count": len(rows)}

    def replay(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM events ORDER BY sequence_number ASC").fetchall()
        return [dict(r) for r in rows]

    def integrity_check(self) -> str:
        row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0])

    def bounded_query(self, *, aggregate_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if aggregate_id:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE aggregate_id=? ORDER BY sequence_number DESC LIMIT ?",
                (aggregate_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY sequence_number DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
