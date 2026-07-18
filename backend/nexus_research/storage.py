"""Storage audit + adapter for nexus_research.

Default: in-memory. Optional: sqlite under NEXUS_DATA_DIR if writable.
No secrets stored. Schema version tracked.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_STORE_LOCK = threading.Lock()
_STORE: "_ResearchStore | None" = None


class _MemoryStore:
    """Append-only in-memory store for research records."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tables: dict[str, list[dict[str, Any]]] = {}

    def append(self, table: str, record: dict[str, Any]) -> None:
        with self._lock:
            self._tables.setdefault(table, []).append(record)

    def query(self, table: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._tables.get(table, [])
            return list(rows[-limit:]) if rows else []

    def count(self, table: str) -> int:
        with self._lock:
            return len(self._tables.get(table, []))

    def clear_table(self, table: str) -> int:
        with self._lock:
            n = len(self._tables.get(table, []))
            self._tables[table] = []
            return n

    @property
    def backend_type(self) -> str:
        return "memory"


class _SqliteStore:
    """Optional sqlite-backed store when NEXUS_DATA_DIR is writable."""

    def __init__(self, db_path: Path) -> None:
        import sqlite3

        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            "  table_name TEXT NOT NULL,"
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  payload TEXT NOT NULL,"
            "  created_at REAL NOT NULL"
            ")"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS kv_table ON kv(table_name, id)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta ("
            "  key TEXT PRIMARY KEY, value TEXT NOT NULL"
            ")"
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO schema_meta VALUES ('version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self._conn.commit()
        self._lock = threading.RLock()

    def append(self, table: str, record: dict[str, Any]) -> None:
        payload = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                "INSERT INTO kv(table_name, payload, created_at) VALUES (?,?,?)",
                (table, payload, time.time()),
            )
            self._conn.commit()

    def query(self, table: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT payload FROM kv WHERE table_name=? ORDER BY id DESC LIMIT ?",
                (table, limit),
            )
            rows = [json.loads(r[0]) for r in cursor.fetchall()]
        rows.reverse()
        return rows

    def count(self, table: str) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT COUNT(*) FROM kv WHERE table_name=?", (table,)
            )
            return int(cursor.fetchone()[0])

    def clear_table(self, table: str) -> int:
        with self._lock:
            n = self.count(table)
            self._conn.execute("DELETE FROM kv WHERE table_name=?", (table,))
            self._conn.commit()
            return n

    @property
    def backend_type(self) -> str:
        return "sqlite"


class _ResearchStore:
    def __init__(self, adapter: _MemoryStore | _SqliteStore) -> None:
        self._adapter = adapter

    def append(self, table: str, record: dict[str, Any]) -> None:
        self._adapter.append(table, record)

    def query(self, table: str, limit: int = 200) -> list[dict[str, Any]]:
        return self._adapter.query(table, limit)

    def count(self, table: str) -> int:
        return self._adapter.count(table)

    def clear_table(self, table: str) -> int:
        return self._adapter.clear_table(table)

    @property
    def backend_type(self) -> str:
        return self._adapter.backend_type


def _build_store() -> _ResearchStore:
    data_dir_env = os.getenv("NEXUS_DATA_DIR", "").strip()
    if data_dir_env:
        try:
            data_dir = Path(data_dir_env)
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "nexus_research.db"
            adapter: _MemoryStore | _SqliteStore = _SqliteStore(db_path)
            logger.info("[nexus_research.storage] sqlite store at %s", db_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[nexus_research.storage] sqlite unavailable (%s); using memory", exc)
            adapter = _MemoryStore()
    else:
        adapter = _MemoryStore()
    return _ResearchStore(adapter)


def get_research_store() -> _ResearchStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = _build_store()
        return _STORE


def storage_audit() -> dict[str, Any]:
    """Return storage audit summary (no secrets)."""
    store = get_research_store()
    tables = ["events", "review_cases", "role_assessments", "research_decisions",
              "review_sessions", "sim_placeholders"]
    counts = {t: store.count(t) for t in tables}
    return {
        "ok": True,
        "schemaVersion": SCHEMA_VERSION,
        "backendType": store.backend_type,
        "researchOnly": True,
        "tableCounts": counts,
        "generatedAt": int(time.time() * 1000),
    }
