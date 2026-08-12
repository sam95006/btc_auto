"""Durable Event Ledger V2 — append-only, hash-chained, idempotent, monotonic.

Uses SQLite WAL with batch-friendly appends. Sequence numbers are strictly
monotonic. Duplicate idempotency keys are ignored (no second write).
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
from typing import Any, Callable

from backend.nexus_runtime.durability_v2.constants import GENESIS_HASH, SCHEMA_VERSION


def _utc(ts: float | None = None) -> str:
    if ts is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class AppendResult:
    status: str
    event_id: str | None
    sequence_number: int | None
    duplicate: bool = False
    reason: str | None = None


class DiskLimitExceeded(Exception):
    """Raised when a soft/hard disk quota is exceeded."""

    def __init__(self, *, kind: str, used: int, limit: int) -> None:
        self.kind = kind
        self.used = used
        self.limit = limit
        super().__init__(f"{kind}: used={used} limit={limit}")


class DurableEventLedgerV2:
    """Hash-chained append-only ledger with fail-closed integrity checks."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], float] | None = None,
        soft_disk_limit_bytes: int | None = None,
        hard_disk_limit_bytes: int | None = None,
        fsync_enabled: bool = True,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._clock = clock or time.time
        self._soft_disk_limit_bytes = soft_disk_limit_bytes
        self._hard_disk_limit_bytes = hard_disk_limit_bytes
        self._fsync_enabled = fsync_enabled
        self._fsync_interrupt = False
        self._last_accepted_wall: float | None = None
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=60.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            try:
                try:
                    self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
                try:
                    self._conn.execute("PRAGMA journal_mode=DELETE")
                except Exception:
                    pass
                self._conn.close()
            except Exception:
                pass

    def set_fsync_interrupt(self, enabled: bool) -> None:
        self._fsync_interrupt = bool(enabled)

    def set_disk_limits(
        self,
        *,
        soft_disk_limit_bytes: int | None = None,
        hard_disk_limit_bytes: int | None = None,
    ) -> None:
        self._soft_disk_limit_bytes = soft_disk_limit_bytes
        self._hard_disk_limit_bytes = hard_disk_limit_bytes

    def _migrate(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ledger_meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              sequence_number INTEGER PRIMARY KEY,
              event_id TEXT NOT NULL UNIQUE,
              aggregate_id TEXT NOT NULL,
              aggregate_type TEXT NOT NULL,
              event_type TEXT NOT NULL,
              previous_event_hash TEXT NOT NULL,
              event_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              wall_clock REAL NOT NULL,
              source TEXT NOT NULL,
              schema_version TEXT NOT NULL,
              idempotency_key TEXT,
              payload_hash TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_v2_idempotency
              ON events(idempotency_key) WHERE idempotency_key IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_v2_agg ON events(aggregate_id, sequence_number);
            """
        )
        cur = self._conn.execute("SELECT value FROM ledger_meta WHERE key='schema_version'")
        if cur.fetchone() is None:
            self._conn.execute(
                "INSERT INTO ledger_meta(key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )
            self._conn.execute(
                "INSERT INTO ledger_meta(key, value) VALUES ('genesis_hash', ?)",
                (GENESIS_HASH,),
            )
            self._conn.execute(
                "INSERT INTO ledger_meta(key, value) VALUES ('next_sequence', ?)",
                ("1",),
            )
        self._conn.commit()

    def _disk_used(self) -> int:
        total = 0
        for p in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")):
            if p.exists():
                total += p.stat().st_size
        return total

    def _check_disk_limits(self, upcoming_bytes: int = 256) -> None:
        used = self._disk_used() + upcoming_bytes
        if self._hard_disk_limit_bytes is not None and used > self._hard_disk_limit_bytes:
            raise DiskLimitExceeded(
                kind="disk_hard_limit", used=used, limit=self._hard_disk_limit_bytes
            )
        if self._soft_disk_limit_bytes is not None and used > self._soft_disk_limit_bytes:
            raise DiskLimitExceeded(
                kind="disk_soft_limit", used=used, limit=self._soft_disk_limit_bytes
            )

    def _last_hash(self) -> str:
        cur = self._conn.execute(
            "SELECT event_hash FROM events ORDER BY sequence_number DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            return row["event_hash"]
        return self._conn.execute(
            "SELECT value FROM ledger_meta WHERE key='genesis_hash'"
        ).fetchone()["value"]

    def _next_sequence(self) -> int:
        row = self._conn.execute(
            "SELECT value FROM ledger_meta WHERE key='next_sequence'"
        ).fetchone()
        return int(row["value"])

    def _bump_sequence(self, next_seq: int) -> None:
        self._conn.execute(
            "UPDATE ledger_meta SET value=? WHERE key='next_sequence'",
            (str(next_seq),),
        )

    def _maybe_fsync(self) -> None:
        if not self._fsync_enabled:
            return
        if self._fsync_interrupt:
            raise InterruptedError("fsync_interruption")
        self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def append(
        self,
        *,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        source: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        wall_clock: float | None = None,
        allow_out_of_order: bool = False,
    ) -> AppendResult:
        banned = {"api_key", "secret", "password", "authorization", "private_key"}
        flat = json.dumps(payload, sort_keys=True, default=str).lower()
        if any(b in flat for b in banned):
            raise ValueError("payload_contains_forbidden_secret_fields")

        payload_json = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        payload_hash = _sha(payload_json)
        wall = float(wall_clock if wall_clock is not None else self._clock())

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
                        sequence_number=int(existing["sequence_number"]),
                        duplicate=True,
                    )

            # Clock rollback detection — refuse silent acceptance.
            if (
                self._last_accepted_wall is not None
                and wall < self._last_accepted_wall
                and not allow_out_of_order
            ):
                return AppendResult(
                    status="BLOCKED_CLOCK_ROLLBACK",
                    event_id=None,
                    sequence_number=None,
                    reason=f"wall={wall} last={self._last_accepted_wall}",
                )

            # Out-of-order (explicit) still appends but is tagged; sequence stays monotonic.
            self._check_disk_limits(len(payload_json) + 256)

            prev = self._last_hash()
            seq = self._next_sequence()
            created_at = _utc(wall)
            event_id = _sha(f"{aggregate_id}|{event_type}|{created_at}|{payload_hash}|{seq}")[:32]
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
                ]
            )
            event_hash = _sha(material)
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(
                    """
                    INSERT INTO events(
                      sequence_number, event_id, aggregate_id, aggregate_type, event_type,
                      previous_event_hash, event_hash, created_at, wall_clock, source,
                      schema_version, idempotency_key, payload_hash, payload_json
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
                        wall,
                        source,
                        SCHEMA_VERSION,
                        idempotency_key,
                        payload_hash,
                        payload_json,
                    ),
                )
                self._bump_sequence(seq + 1)
                self._conn.commit()
                self._maybe_fsync()
            except InterruptedError:
                # Simulate fsync interruption after commit intent — leave WAL dirty.
                raise
            except DiskLimitExceeded:
                self._conn.rollback()
                raise
            except Exception:
                self._conn.rollback()
                raise

            self._last_accepted_wall = wall
            return AppendResult(
                status="APPENDED",
                event_id=event_id,
                sequence_number=seq,
                duplicate=False,
                reason="out_of_order" if allow_out_of_order else None,
            )

    def append_many(
        self,
        items: list[dict[str, Any]],
        *,
        commit_every: int = 2000,
        latency_sink: list[float] | None = None,
    ) -> dict[str, Any]:
        """High-throughput batch append for scale. Still hash-chained + idempotent."""
        appended = 0
        duplicates = 0
        with self._lock:
            prev = self._last_hash()
            seq = self._next_sequence() - 1
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for item in items:
                    t0 = time.perf_counter()
                    idem = item.get("idempotency_key")
                    if idem:
                        cur = self._conn.execute(
                            "SELECT event_id, sequence_number FROM events WHERE idempotency_key=?",
                            (idem,),
                        )
                        if cur.fetchone():
                            duplicates += 1
                            if latency_sink is not None:
                                latency_sink.append(time.perf_counter() - t0)
                            continue

                    payload = item.get("payload") or {}
                    payload_json = json.dumps(
                        payload, sort_keys=True, default=str, separators=(",", ":")
                    )
                    self._check_disk_limits(len(payload_json) + 256)
                    payload_hash = _sha(payload_json)
                    wall = float(item.get("wall_clock") if item.get("wall_clock") is not None else self._clock())
                    if (
                        self._last_accepted_wall is not None
                        and wall < self._last_accepted_wall
                        and not item.get("allow_out_of_order")
                    ):
                        # Fail closed on clock rollback inside batch.
                        self._conn.rollback()
                        return {
                            "status": "BLOCKED_CLOCK_ROLLBACK",
                            "appended": appended,
                            "duplicates": duplicates,
                        }

                    seq += 1
                    created_at = _utc(wall)
                    event_id = _sha(
                        f"{item['aggregate_id']}|{item['event_type']}|{created_at}|{payload_hash}|{seq}"
                    )[:32]
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
                        ]
                    )
                    event_hash = _sha(material)
                    self._conn.execute(
                        """
                        INSERT INTO events(
                          sequence_number, event_id, aggregate_id, aggregate_type, event_type,
                          previous_event_hash, event_hash, created_at, wall_clock, source,
                          schema_version, idempotency_key, payload_hash, payload_json
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
                            wall,
                            item.get("source") or "scale",
                            SCHEMA_VERSION,
                            idem,
                            payload_hash,
                            payload_json,
                        ),
                    )
                    prev = event_hash
                    self._last_accepted_wall = wall
                    appended += 1
                    if latency_sink is not None:
                        latency_sink.append(time.perf_counter() - t0)
                    if appended % commit_every == 0:
                        self._bump_sequence(seq + 1)
                        self._conn.commit()
                        self._conn.execute("BEGIN IMMEDIATE")
                self._bump_sequence(seq + 1)
                self._conn.commit()
                if self._fsync_enabled and not self._fsync_interrupt:
                    self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except DiskLimitExceeded:
                self._conn.rollback()
                raise
            except Exception:
                self._conn.rollback()
                raise
        return {"status": "OK", "appended": appended, "duplicates": duplicates}

    def event_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"])

    def max_sequence(self) -> int | None:
        row = self._conn.execute(
            "SELECT MAX(sequence_number) AS m FROM events"
        ).fetchone()
        if row is None or row["m"] is None:
            return None
        return int(row["m"])

    def verify_hash_chain(self) -> dict[str, Any]:
        rows = self._conn.execute(
            "SELECT sequence_number, previous_event_hash, event_hash, event_id, aggregate_id, "
            "aggregate_type, event_type, created_at, source, schema_version, idempotency_key, "
            "payload_hash FROM events ORDER BY sequence_number ASC"
        ).fetchall()
        prev = self._conn.execute(
            "SELECT value FROM ledger_meta WHERE key='genesis_hash'"
        ).fetchone()["value"]
        expected_seq = 1
        for row in rows:
            if int(row["sequence_number"]) != expected_seq:
                return {
                    "ledger_hash_chain_status": "CORRUPTION_DETECTED",
                    "reason": "non_monotonic_sequence",
                    "broken_at_sequence": row["sequence_number"],
                    "expected_sequence": expected_seq,
                }
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
                ]
            )
            expected = _sha(material)
            if row["previous_event_hash"] != prev or row["event_hash"] != expected:
                return {
                    "ledger_hash_chain_status": "CORRUPTION_DETECTED",
                    "reason": "hash_mismatch",
                    "broken_at_sequence": row["sequence_number"],
                }
            prev = row["event_hash"]
            expected_seq += 1
        return {"ledger_hash_chain_status": "PASS", "event_count": len(rows)}

    def replay(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        if limit is None:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY sequence_number ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY sequence_number ASC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def integrity_check(self) -> str:
        try:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
            return str(row[0])
        except Exception as exc:
            return f"error:{exc}"

    def truncate_tail_bytes(self, nbytes: int) -> None:
        """Fault injection: truncate ledger file (caller must close first ideally)."""
        with self._lock:
            self._conn.commit()
        # Truncation of sqlite main db while open is unsafe; expose for closed-handle drills.
        raise RuntimeError("use_fault_injectors.truncate_file_on_closed_ledger")

    def corrupt_hash_at(self, sequence_number: int) -> bool:
        """Fault injection: flip stored event_hash for a sequence (detectable)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT event_hash FROM events WHERE sequence_number=?",
                (sequence_number,),
            )
            row = cur.fetchone()
            if not row:
                return False
            bad = ("f" if row["event_hash"][0] != "f" else "0") + row["event_hash"][1:]
            self._conn.execute(
                "UPDATE events SET event_hash=? WHERE sequence_number=?",
                (bad, sequence_number),
            )
            self._conn.commit()
            return True

    def flip_bit_in_payload(self, sequence_number: int) -> bool:
        """Fault injection: mutate payload_json without updating hashes."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT payload_json FROM events WHERE sequence_number=?",
                (sequence_number,),
            )
            row = cur.fetchone()
            if not row:
                return False
            raw = row["payload_json"]
            flipped = (raw[:-1] + ("X" if not raw.endswith("X") else "Y")) if raw else "X"
            self._conn.execute(
                "UPDATE events SET payload_json=? WHERE sequence_number=?",
                (flipped, sequence_number),
            )
            self._conn.commit()
            return True
