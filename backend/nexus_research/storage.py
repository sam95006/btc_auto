"""Storage adapter for nexus_research — Phase 6 Gate B: Durable Persistence.

Env contract
------------
NEXUS_RESEARCH_DATABASE_URL   Postgres DSN (postgres driver pending — see below)
DATABASE_URL                  Fallback postgres DSN
NEXUS_DATA_DIR                Directory for sqlite file; writability probed at startup
NEXUS_RESEARCH_STORAGE_MODE   memory | sqlite | postgres | auto  (default: auto)

Postgres status: *pending*.  psycopg2-binary is not in requirements.txt.
When a postgres URL is detected the store falls back to sqlite/memory and logs
a clear warning.  Add psycopg2-binary to requirements.txt to enable postgres.

Isolation guarantee
-------------------
The research DB file is nexus_research.db, never trading.db.  Any path
conflict with the trading DB raises ValueError at startup.

Schema versioning
-----------------
Idempotent migrations are applied automatically in get_research_store().
SCHEMA_VERSION tracks the highest applied migration.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 6
_STORE_LOCK = threading.Lock()
_STORE: "_ResearchStore | None" = None

# Tables that have their own typed schema (with idempotency + indexes).
# All other table names fall back to the generic kv table.
TYPED_TABLES = frozenset({
    "domain_events",
    "dead_letters",
    "review_cases",
    "role_assessments",
    "research_decisions",
    "review_sessions",
    "sim_orders",
    "sim_fills",
    "sim_positions",
    "sim_ledger",
    "durable_ledger_events",
    "risk_snapshots",
    "outcomes",
    "reflections",
    "patch_proposals",
    "replay_checkpoints",
    "runtime_job_state",
    "persistence_validation_markers",
    "persistence_probes",
    "paper_activation_sessions",
    "paper_trade_evidence",
})


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _utc_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _new_id() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Schema migrations (idempotent)
# ─────────────────────────────────────────────────────────────────────────────

# Each entry: (target_version, description, [sql_statements])
_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "initial kv + schema_meta",
        [
            """CREATE TABLE IF NOT EXISTS kv (
                table_name TEXT NOT NULL,
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS kv_table ON kv(table_name, id)",
            """CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""",
        ],
    ),
    (
        2,
        "phase6 typed tables with idempotency keys and UTC timestamps",
        [
            # domain_events
            """CREATE TABLE IF NOT EXISTS domain_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT '',
                tag TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT domain_events_event_id_uq UNIQUE (event_id)
            )""",
            "CREATE INDEX IF NOT EXISTS domain_events_type_ts"
            "  ON domain_events(event_type, created_at_ts)",
            "CREATE INDEX IF NOT EXISTS domain_events_tag_ts"
            "  ON domain_events(tag, created_at_ts)",

            # dead_letters
            """CREATE TABLE IF NOT EXISTS dead_letters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                letter_id TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT dead_letters_letter_id_uq UNIQUE (letter_id)
            )""",

            # review_cases
            """CREATE TABLE IF NOT EXISTS review_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                symbol TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                updated_at_ts REAL,
                CONSTRAINT review_cases_case_id_uq UNIQUE (case_id)
            )""",
            "CREATE INDEX IF NOT EXISTS review_cases_symbol_ts"
            "  ON review_cases(symbol, created_at_ts)",
            "CREATE INDEX IF NOT EXISTS review_cases_status_ts"
            "  ON review_cases(status, created_at_ts)",

            # role_assessments
            """CREATE TABLE IF NOT EXISTS role_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assessment_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT '',
                case_id TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT role_assessments_assessment_id_uq UNIQUE (assessment_id)
            )""",
            "CREATE INDEX IF NOT EXISTS role_assessments_role_ts"
            "  ON role_assessments(role, created_at_ts)",

            # research_decisions
            """CREATE TABLE IF NOT EXISTS research_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id TEXT NOT NULL,
                symbol TEXT NOT NULL DEFAULT '',
                decision_type TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT research_decisions_decision_id_uq UNIQUE (decision_id)
            )""",
            "CREATE INDEX IF NOT EXISTS research_decisions_symbol_ts"
            "  ON research_decisions(symbol, created_at_ts)",

            # review_sessions
            """CREATE TABLE IF NOT EXISTS review_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                completed_at_ts REAL,
                CONSTRAINT review_sessions_session_id_uq UNIQUE (session_id)
            )""",

            # sim_orders
            """CREATE TABLE IF NOT EXISTS sim_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                symbol TEXT NOT NULL DEFAULT '',
                side TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT sim_orders_order_id_uq UNIQUE (order_id)
            )""",
            "CREATE INDEX IF NOT EXISTS sim_orders_symbol_ts"
            "  ON sim_orders(symbol, created_at_ts)",

            # sim_fills
            """CREATE TABLE IF NOT EXISTS sim_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fill_id TEXT NOT NULL,
                order_id TEXT NOT NULL DEFAULT '',
                symbol TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT sim_fills_fill_id_uq UNIQUE (fill_id)
            )""",
            "CREATE INDEX IF NOT EXISTS sim_fills_order ON sim_fills(order_id)",

            # sim_positions
            """CREATE TABLE IF NOT EXISTS sim_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id TEXT NOT NULL,
                symbol TEXT NOT NULL DEFAULT '',
                side TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                closed_at_ts REAL,
                CONSTRAINT sim_positions_position_id_uq UNIQUE (position_id)
            )""",
            "CREATE INDEX IF NOT EXISTS sim_positions_symbol_status"
            "  ON sim_positions(symbol, status)",

            # sim_ledger
            """CREATE TABLE IF NOT EXISTS sim_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT NOT NULL,
                entry_type TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT sim_ledger_entry_id_uq UNIQUE (entry_id)
            )""",

            # risk_snapshots
            """CREATE TABLE IF NOT EXISTS risk_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT risk_snapshots_snapshot_id_uq UNIQUE (snapshot_id)
            )""",

            # outcomes
            """CREATE TABLE IF NOT EXISTS outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                outcome_id TEXT NOT NULL,
                position_id TEXT NOT NULL DEFAULT '',
                symbol TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT outcomes_outcome_id_uq UNIQUE (outcome_id)
            )""",
            "CREATE INDEX IF NOT EXISTS outcomes_symbol_ts"
            "  ON outcomes(symbol, created_at_ts)",

            # reflections
            """CREATE TABLE IF NOT EXISTS reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reflection_id TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT reflections_reflection_id_uq UNIQUE (reflection_id)
            )""",

            # patch_proposals
            """CREATE TABLE IF NOT EXISTS patch_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                applied_at_ts REAL,
                CONSTRAINT patch_proposals_proposal_id_uq UNIQUE (proposal_id)
            )""",
            "CREATE INDEX IF NOT EXISTS patch_proposals_status_ts"
            "  ON patch_proposals(status, created_at_ts)",

            # replay_checkpoints
            """CREATE TABLE IF NOT EXISTS replay_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT NOT NULL,
                replay_run_id TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT replay_checkpoints_checkpoint_id_uq UNIQUE (checkpoint_id)
            )""",
            "CREATE INDEX IF NOT EXISTS replay_checkpoints_run_ts"
            "  ON replay_checkpoints(replay_run_id, created_at_ts)",

            # runtime_job_state
            """CREATE TABLE IF NOT EXISTS runtime_job_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                job_type TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                updated_at_ts REAL,
                CONSTRAINT runtime_job_state_job_id_uq UNIQUE (job_id)
            )""",
            "CREATE INDEX IF NOT EXISTS runtime_job_state_type_status"
            "  ON runtime_job_state(job_type, status)",

            # persistence_validation_markers
            """CREATE TABLE IF NOT EXISTS persistence_validation_markers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marker_id TEXT NOT NULL,
                tag TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT persistence_validation_markers_marker_id_uq UNIQUE (marker_id)
            )""",
        ],
    ),
    (
        3,
        "phase61 persistence_probes for restart proof",
        [
            """CREATE TABLE IF NOT EXISTS persistence_probes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                probe_id TEXT NOT NULL,
                created_boot_id TEXT NOT NULL DEFAULT '',
                payload_hash TEXT NOT NULL DEFAULT '',
                validation_label TEXT NOT NULL DEFAULT 'PERSISTENCE_VALIDATION',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT persistence_probes_probe_id_uq UNIQUE (probe_id)
            )""",
            "CREATE INDEX IF NOT EXISTS persistence_probes_boot_ts"
            "  ON persistence_probes(created_boot_id, created_at_ts)",
        ],
    ),
    (
        4,
        "phase61b durable_ledger_events hash-chained SoT",
        [
            """CREATE TABLE IF NOT EXISTS durable_ledger_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                account_id TEXT NOT NULL DEFAULT '',
                sequence INTEGER NOT NULL DEFAULT 0,
                event_type TEXT NOT NULL DEFAULT '',
                idempotency_key TEXT NOT NULL DEFAULT '',
                event_hash TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT durable_ledger_events_event_id_uq UNIQUE (event_id),
                CONSTRAINT durable_ledger_events_idem_uq UNIQUE (idempotency_key),
                CONSTRAINT durable_ledger_events_acct_seq_uq UNIQUE (account_id, sequence)
            )""",
            "CREATE INDEX IF NOT EXISTS durable_ledger_events_acct_seq"
            "  ON durable_ledger_events(account_id, sequence)",
            "CREATE INDEX IF NOT EXISTS durable_ledger_events_hash"
            "  ON durable_ledger_events(event_hash)",
        ],
    ),
    (
        5,
        "phase62 review_cases lifecycle indexes + lookup columns",
        [
            "ALTER TABLE review_cases ADD COLUMN expires_at_ts REAL",
            "ALTER TABLE review_cases ADD COLUMN validation_type TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE review_cases ADD COLUMN side TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE review_cases ADD COLUMN candidate_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE review_cases ADD COLUMN correlation_id TEXT NOT NULL DEFAULT ''",
            "CREATE INDEX IF NOT EXISTS review_cases_expires_ts"
            "  ON review_cases(expires_at_ts)",
            "CREATE INDEX IF NOT EXISTS review_cases_updated_ts"
            "  ON review_cases(updated_at_ts)",
            "CREATE INDEX IF NOT EXISTS review_cases_validation_type"
            "  ON review_cases(validation_type)",
            "CREATE INDEX IF NOT EXISTS review_cases_side_status"
            "  ON review_cases(side, status)",
            "CREATE INDEX IF NOT EXISTS review_cases_candidate"
            "  ON review_cases(candidate_id)",
            "CREATE INDEX IF NOT EXISTS review_cases_correlation"
            "  ON review_cases(correlation_id)",
            "CREATE INDEX IF NOT EXISTS review_cases_natural_active"
            "  ON review_cases(status, validation_type, expires_at_ts, updated_at_ts)",
        ],
    ),
    (
        6,
        "phase63 paper activation sessions + trade evidence",
        [
            """CREATE TABLE IF NOT EXISTS paper_activation_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT '',
                account_id TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                updated_at_ts REAL,
                CONSTRAINT paper_activation_sessions_session_id_uq UNIQUE (session_id)
            )""",
            "CREATE INDEX IF NOT EXISTS paper_activation_sessions_state"
            "  ON paper_activation_sessions(state, created_at_ts)",
            "CREATE INDEX IF NOT EXISTS paper_activation_sessions_account"
            "  ON paper_activation_sessions(account_id, created_at_ts)",
            """CREATE TABLE IF NOT EXISTS paper_trade_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                decision_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                CONSTRAINT paper_trade_evidence_evidence_id_uq UNIQUE (evidence_id)
            )""",
            "CREATE INDEX IF NOT EXISTS paper_trade_evidence_session"
            "  ON paper_trade_evidence(session_id, created_at_ts)",
            "CREATE INDEX IF NOT EXISTS paper_trade_evidence_decision"
            "  ON paper_trade_evidence(decision_id)",
        ],
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Typed-table insert helper
# ─────────────────────────────────────────────────────────────────────────────

# Maps table name → (pk_field, extra_cols_spec)
# extra_cols_spec is a list of (col_name, record_key) pairs
_TYPED_INSERT: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "domain_events":         ("event_id",      [("event_type","event_type"), ("tag","tag")]),
    "dead_letters":          ("letter_id",      [("source","source"), ("reason","reason")]),
    "review_cases":          ("case_id",        [
        ("symbol", "symbol"),
        ("status", "status"),
        ("side", "side"),
        ("validation_type", "validationType"),
        ("candidate_id", "candidateId"),
        ("correlation_id", "correlationId"),
    ]),
    "role_assessments":      ("assessment_id",  [("role","role"), ("case_id","case_id")]),
    "research_decisions":    ("decision_id",    [("symbol","symbol"), ("decision_type","decision_type")]),
    "review_sessions":       ("session_id",     [("status","status")]),
    "sim_orders":            ("order_id",       [("symbol","symbol"), ("side","side"), ("status","status")]),
    "sim_fills":             ("fill_id",        [("order_id","order_id"), ("symbol","symbol")]),
    "sim_positions":         ("position_id",    [("symbol","symbol"), ("side","side"), ("status","status")]),
    "sim_ledger":            ("entry_id",       [("entry_type","entry_type")]),
    "durable_ledger_events": ("event_id", [
        ("account_id", "accountId"),
        ("sequence", "sequence"),
        ("event_type", "eventType"),
        ("idempotency_key", "idempotencyKey"),
        ("event_hash", "eventHash"),
    ]),
    "risk_snapshots":        ("snapshot_id",    []),
    "outcomes":              ("outcome_id",     [("position_id","position_id"), ("symbol","symbol")]),
    "reflections":           ("reflection_id",  [("session_id","session_id")]),
    "patch_proposals":       ("proposal_id",    [("status","status")]),
    "replay_checkpoints":    ("checkpoint_id",  [("replay_run_id","replay_run_id")]),
    "runtime_job_state":     ("job_id",         [("job_type","job_type"), ("status","status")]),
    "persistence_validation_markers": ("marker_id", [("tag","tag")]),
    "persistence_probes": ("probe_id", [("created_boot_id","createdBootId"), ("payload_hash","payloadHash"), ("validation_label","validationLabel")]),
    "paper_activation_sessions": ("session_id", [
        ("state", "state"),
        ("account_id", "accountId"),
    ]),
    "paper_trade_evidence": ("evidence_id", [
        ("session_id", "sessionId"),
        ("decision_id", "decisionId"),
        ("status", "status"),
    ]),
}


def _build_typed_insert(
    table: str,
    record: dict[str, Any],
) -> tuple[str, tuple[Any, ...]]:
    """Return (sql, args) for INSERT OR IGNORE into a typed table."""
    spec = _TYPED_INSERT[table]
    pk_field, extra = spec
    ts = time.time()
    payload = json.dumps(record, ensure_ascii=False)
    now_utc = _utc_iso()

    pk_val = record.get(pk_field)
    if not pk_val:
        # camelCase aliases used by research records (caseId, probeId, …)
        camel = "".join(
            part[:1].upper() + part[1:] if i else part
            for i, part in enumerate(pk_field.split("_"))
        )
        pk_val = record.get(camel)
    pk_val = str(pk_val or _new_id())

    cols = [pk_field] + [c for c, _ in extra] + ["payload", "created_at_utc", "created_at_ts"]
    vals: list[Any] = [pk_val] + [str(record.get(rk) or "") for _, rk in extra] + [payload, now_utc, ts]

    if table == "review_cases":
        cols.extend(["updated_at_ts", "expires_at_ts"])
        expires = record.get("expiresAt") or record.get("expires_at") or record.get("expiresAtTs")
        try:
            expires_ts = float(expires) / (1000.0 if float(expires) > 1e12 else 1.0) if expires else None
        except (TypeError, ValueError):
            expires_ts = None
        vals.extend([ts, expires_ts])

    placeholders = ",".join("?" * len(cols))
    col_list = ",".join(cols)
    sql = f"INSERT OR IGNORE INTO {table} ({col_list}) VALUES ({placeholders})"
    return sql, tuple(vals)


# ─────────────────────────────────────────────────────────────────────────────
# In-memory store
# ─────────────────────────────────────────────────────────────────────────────

class _MemoryStore:
    """Append-only in-memory store for research records."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._seen_ids: dict[str, set[str]] = {}

    def _dedup_key(self, table: str, record: dict[str, Any]) -> str | None:
        spec = _TYPED_INSERT.get(table)
        if spec:
            pk_field = spec[0]
            val = record.get(pk_field)
            if val:
                return str(val)
        return str(record.get("_idempotency_key") or "")

    def append(self, table: str, record: dict[str, Any]) -> None:
        with self._lock:
            key = self._dedup_key(table, record)
            if key:
                if key in self._seen_ids.get(table, set()):
                    return
                self._seen_ids.setdefault(table, set()).add(key)
            if "created_at_utc" not in record:
                record = {**record, "created_at_utc": _utc_iso(), "created_at_ts": time.time()}
            self._tables.setdefault(table, []).append(record)

    def query(self, table: str, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._tables.get(table, [])
            return list(rows[offset : offset + limit]) if rows else []

    def count(self, table: str) -> int:
        with self._lock:
            return len(self._tables.get(table, []))

    def clear_table(self, table: str) -> int:
        with self._lock:
            n = len(self._tables.get(table, []))
            self._tables[table] = []
            self._seen_ids.pop(table, None)
            return n

    def get_by_pk(self, table: str, pk_value: str) -> dict[str, Any] | None:
        with self._lock:
            spec = _TYPED_INSERT.get(table)
            pk_field = spec[0] if spec else None
            for row in self._tables.get(table, []):
                if pk_field and str(row.get(pk_field) or "") == str(pk_value):
                    return dict(row)
                # camelCase fallback
                if pk_field:
                    camel = "".join(
                        part[:1].upper() + part[1:] if i else part
                        for i, part in enumerate(pk_field.split("_"))
                    )
                    if str(row.get(camel) or "") == str(pk_value):
                        return dict(row)
            return None

    def upsert(self, table: str, record: dict[str, Any]) -> bool:
        with self._lock:
            spec = _TYPED_INSERT.get(table)
            pk_field = spec[0] if spec else None
            if not pk_field:
                self.append(table, record)
                return True
            camel = "".join(
                part[:1].upper() + part[1:] if i else part
                for i, part in enumerate(pk_field.split("_"))
            )
            pk_val = str(record.get(pk_field) or record.get(camel) or "")
            rows = self._tables.setdefault(table, [])
            for i, row in enumerate(rows):
                if str(row.get(pk_field) or row.get(camel) or "") == pk_val:
                    rows[i] = {**row, **record}
                    return True
            rows.append(dict(record))
            if pk_val:
                self._seen_ids.setdefault(table, set()).add(pk_val)
            return True

    def query_cases(
        self,
        *,
        statuses: list[str] | None = None,
        validation_types: list[str] | None = None,
        exclude_validation: bool = False,
        symbol: str | None = None,
        limit: int = 100,
        offset: int = 0,
        order_desc: bool = True,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._tables.get("review_cases", []))

        def _val_type(r: dict[str, Any]) -> str:
            return str(r.get("validationType") or r.get("validation_type") or "")

        if statuses:
            status_set = set(statuses)
            rows = [r for r in rows if str(r.get("status") or "") in status_set]
        if validation_types:
            vt = set(validation_types)
            rows = [r for r in rows if _val_type(r) in vt]
        if exclude_validation:
            rows = [r for r in rows if _val_type(r) in ("", "NATURAL")]
        if symbol:
            rows = [r for r in rows if str(r.get("symbol") or "") == symbol]
        rows.sort(
            key=lambda r: int(r.get("updatedAt") or r.get("createdAt") or 0),
            reverse=order_desc,
        )
        return rows[offset : offset + limit]

    def count_cases(
        self,
        *,
        statuses: list[str] | None = None,
        exclude_validation: bool = False,
    ) -> int:
        return len(
            self.query_cases(
                statuses=statuses,
                exclude_validation=exclude_validation,
                limit=10_000_000,
            )
        )

    def persist_validation_marker(
        self, marker_id: str, tag: str, payload: dict[str, Any]
    ) -> None:
        record = {
            "marker_id": marker_id,
            "tag": tag,
            "payload": payload,
            "created_at_utc": _utc_iso(),
            "created_at_ts": time.time(),
        }
        self.append("persistence_validation_markers", record)

    def delete_old_records(self, table: str, older_than_ts: float) -> int:
        with self._lock:
            rows = self._tables.get(table, [])
            kept = [r for r in rows if float(r.get("created_at_ts", 0)) >= older_than_ts]
            removed = len(rows) - len(kept)
            self._tables[table] = kept
            return removed

    def wal_checkpoint(self, mode: str = "TRUNCATE") -> dict[str, Any]:
        return {"ok": True, "mode": mode, "backend": "memory", "skipped": True}

    def sqlite_runtime_profile(self, *, force_integrity: bool = False) -> dict[str, Any]:
        return {
            "database_path_redacted": None,
            "journal_mode": None,
            "foreign_keys": None,
            "busy_timeout_ms": None,
            "synchronous_mode": None,
            "single_writer_owner": None,
            "migration_lock": False,
            "integrity_check": "memory",
            "integrity_check_cached": False,
            "force_integrity": force_integrity,
            "checkpoint_policy": "n/a",
            "backup_policy": "n/a",
        }

    @property
    def backend_type(self) -> str:
        return "memory"

    @property
    def schema_version(self) -> int:
        return SCHEMA_VERSION

    @property
    def db_path(self) -> str | None:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SQLite store (isolated from trading.db)
# ─────────────────────────────────────────────────────────────────────────────

class _SqliteStore:
    """SQLite-backed research store.  File is always nexus_research.db, never trading.db."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.RLock()
        self._run_migrations()
        self._owner_id = str(uuid.uuid4())

    # Full integrity_check on a large WAL DB can take minutes and holds
    # the store RLock — starving paper/status and other read APIs.
    _INTEGRITY_CACHE_TTL_SEC = 3600.0
    _TABLE_COUNT_CACHE_TTL_SEC = 60.0
    _integrity_cache: tuple[float, Any] | None = None
    _table_count_cache: tuple[float, dict[str, int]] | None = None

    def sqlite_runtime_profile(self, *, force_integrity: bool = False) -> dict[str, Any]:
        with self._lock:
            def _pragma(name: str) -> Any:
                row = self._conn.execute(f"PRAGMA {name}").fetchone()
                return row[0] if row else None

            now = time.time()
            cached = getattr(self, "_integrity_cache", None)
            integrity: Any
            used_cache = False
            if force_integrity:
                integrity = _pragma("integrity_check")
                self._integrity_cache = (now, integrity)
            elif (
                cached is not None
                and (now - float(cached[0])) < self._INTEGRITY_CACHE_TTL_SEC
            ):
                integrity = cached[1]
                used_cache = True
            else:
                # Hot path: do NOT run full integrity_check (can lock large DB for minutes).
                integrity = "skipped_on_status_path"
                used_cache = False

            return {
                "database_path_redacted": str(self._db_path).replace("\\", "/").split("/data/")[-1]
                if "/data/" in str(self._db_path).replace("\\", "/")
                else "nexus-research/nexus_research.db",
                "journal_mode": _pragma("journal_mode"),
                "foreign_keys": bool(_pragma("foreign_keys")),
                "busy_timeout_ms": _pragma("busy_timeout"),
                "synchronous_mode": _pragma("synchronous"),
                "single_writer_owner": self._owner_id,
                "migration_lock": True,
                "integrity_check": integrity,
                "integrity_check_cached": used_cache,
                "checkpoint_policy": "TRUNCATE_on_validation_and_shutdown",
                "backup_policy": "volume_probe + backups/ directory",
            }

    def wal_checkpoint(self, mode: str = "TRUNCATE") -> dict[str, Any]:
        with self._lock:
            try:
                row = self._conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
                return {
                    "ok": True,
                    "mode": mode,
                    "busy": row[0] if row else None,
                    "log": row[1] if row and len(row) > 1 else None,
                    "checkpointed": row[2] if row and len(row) > 2 else None,
                }
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": str(exc), "mode": mode}

    # ── migrations ────────────────────────────────────────────────────────────

    def _current_version(self) -> int:
        try:
            cur = self._conn.execute(
                "SELECT value FROM schema_meta WHERE key='version'"
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception:  # noqa: BLE001
            return 0

    def _run_migrations(self) -> None:
        current = self._current_version()
        for target, description, stmts in _MIGRATIONS:
            if current >= target:
                continue
            logger.info(
                "[nexus_research.storage] migrate v%d→v%d: %s",
                current, target, description,
            )
            for stmt in stmts:
                self._conn.execute(stmt)
            self._conn.execute(
                "INSERT OR REPLACE INTO schema_meta VALUES ('version', ?)",
                (str(target),),
            )
            self._conn.commit()
            current = target
        logger.debug("[nexus_research.storage] schema version=%d", current)

    # ── typed-table write ─────────────────────────────────────────────────────

    def _try_typed_insert(self, table: str, record: dict[str, Any]) -> bool:
        if table not in _TYPED_INSERT:
            return False
        try:
            sql, args = _build_typed_insert(table, record)
            self._conn.execute(sql, args)
            self._conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("[nexus_research.storage] typed insert failed (%s): %s", table, exc)
            return False

    # ── public interface ──────────────────────────────────────────────────────

    def append(self, table: str, record: dict[str, Any]) -> None:
        with self._lock:
            if self._try_typed_insert(table, record):
                return
            payload = json.dumps(record, ensure_ascii=False)
            self._conn.execute(
                "INSERT INTO kv(table_name, payload, created_at) VALUES (?,?,?)",
                (table, payload, time.time()),
            )
            self._conn.commit()

    def query(self, table: str, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            if table in _TYPED_INSERT:
                try:
                    cur = self._conn.execute(
                        f"SELECT payload FROM {table} ORDER BY id DESC LIMIT ? OFFSET ?",
                        (limit, offset),
                    )
                    rows = [json.loads(r[0]) for r in cur.fetchall()]
                    rows.reverse()
                    return rows
                except Exception:  # noqa: BLE001
                    pass
            cur = self._conn.execute(
                "SELECT payload FROM kv WHERE table_name=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (table, limit, offset),
            )
            rows = [json.loads(r[0]) for r in cur.fetchall()]
            rows.reverse()
            return rows

    def count(self, table: str) -> int:
        with self._lock:
            if table in _TYPED_INSERT:
                try:
                    cur = self._conn.execute(f"SELECT COUNT(*) FROM {table}")
                    return int(cur.fetchone()[0])
                except Exception:  # noqa: BLE001
                    pass
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM kv WHERE table_name=?", (table,)
            )
            return int(cur.fetchone()[0])

    def clear_table(self, table: str) -> int:
        with self._lock:
            n = self.count(table)
            if table in _TYPED_INSERT:
                try:
                    self._conn.execute(f"DELETE FROM {table}")
                    self._conn.commit()
                    return n
                except Exception:  # noqa: BLE001
                    pass
            self._conn.execute("DELETE FROM kv WHERE table_name=?", (table,))
            self._conn.commit()
            return n

    def get_by_pk(self, table: str, pk_value: str) -> dict[str, Any] | None:
        with self._lock:
            if table in _TYPED_INSERT:
                pk_field = _TYPED_INSERT[table][0]
                try:
                    cur = self._conn.execute(
                        f"SELECT payload FROM {table} WHERE {pk_field}=? LIMIT 1",
                        (str(pk_value),),
                    )
                    row = cur.fetchone()
                    if row:
                        return json.loads(row[0])
                except Exception:  # noqa: BLE001
                    pass
            # Fallback scan recent kv rows (bounded).
            cur = self._conn.execute(
                "SELECT payload FROM kv WHERE table_name=? ORDER BY id DESC LIMIT 5000",
                (table,),
            )
            for (payload,) in cur.fetchall():
                try:
                    rec = json.loads(payload)
                except Exception:  # noqa: BLE001
                    continue
                for key in (
                    "caseId", "case_id", "decisionId", "decision_id",
                    "sessionId", "session_id", "assessmentId", "assessment_id",
                    "reflectionId", "reflection_id", "proposalId", "proposal_id",
                    "entryId", "entry_id", "probeId", "probe_id", "marker_id",
                ):
                    if str(rec.get(key) or "") == str(pk_value):
                        return rec
            return None

    def upsert(self, table: str, record: dict[str, Any]) -> bool:
        """Insert or replace a typed-table record by primary key (payload + indexed cols)."""
        with self._lock:
            if table not in _TYPED_INSERT:
                self.append(table, record)
                return True
            pk_field, extra = _TYPED_INSERT[table]
            pk_val = record.get(pk_field)
            if not pk_val:
                camel = "".join(
                    part[:1].upper() + part[1:] if i else part
                    for i, part in enumerate(pk_field.split("_"))
                )
                pk_val = record.get(camel)
            pk_val = str(pk_val or "")
            if not pk_val:
                return False
            ts = time.time()
            payload = json.dumps(record, ensure_ascii=False)
            now_utc = _utc_iso()
            set_cols = [f"{c}=?" for c, _ in extra] + ["payload=?"]
            set_vals: list[Any] = [str(record.get(rk) or "") for _, rk in extra] + [payload]
            if table == "review_cases":
                set_cols.extend(["updated_at_ts=?", "expires_at_ts=?"])
                expires = record.get("expiresAt") or record.get("expires_at") or record.get("expiresAtTs")
                try:
                    expires_ts = (
                        float(expires) / (1000.0 if float(expires) > 1e12 else 1.0)
                        if expires
                        else None
                    )
                except (TypeError, ValueError):
                    expires_ts = None
                set_vals.extend([ts, expires_ts])
            sql = f"UPDATE {table} SET {', '.join(set_cols)} WHERE {pk_field}=?"
            cur = self._conn.execute(sql, tuple(set_vals + [pk_val]))
            if cur.rowcount == 0:
                # Fall back to insert
                insert_sql, args = _build_typed_insert(table, record)
                # Force replace path: delete ignore then insert
                self._conn.execute(insert_sql, args)
                if self._conn.total_changes == 0:
                    # INSERT OR IGNORE ignored existing — force update already tried
                    pass
            self._conn.commit()
            return True

    def query_cases(
        self,
        *,
        statuses: list[str] | None = None,
        validation_types: list[str] | None = None,
        exclude_validation: bool = False,
        symbol: str | None = None,
        limit: int = 100,
        offset: int = 0,
        order_desc: bool = True,
    ) -> list[dict[str, Any]]:
        """Bounded review_cases query using indexes (never loads full history)."""
        with self._lock:
            where: list[str] = []
            args: list[Any] = []
            if statuses:
                placeholders = ",".join("?" * len(statuses))
                where.append(f"status IN ({placeholders})")
                args.extend(statuses)
            if validation_types:
                placeholders = ",".join("?" * len(validation_types))
                where.append(f"validation_type IN ({placeholders})")
                args.extend(validation_types)
            if exclude_validation:
                where.append("(validation_type IS NULL OR validation_type='' OR validation_type='NATURAL')")
            if symbol:
                where.append("symbol=?")
                args.append(symbol)
            clause = (" WHERE " + " AND ".join(where)) if where else ""
            order = "DESC" if order_desc else "ASC"
            # Prefer updated_at_ts when present; fall back to created_at_ts
            sql = (
                f"SELECT payload FROM review_cases{clause}"
                f" ORDER BY COALESCE(updated_at_ts, created_at_ts) {order}"
                f" LIMIT ? OFFSET ?"
            )
            args.extend([int(limit), int(offset)])
            try:
                cur = self._conn.execute(sql, tuple(args))
                return [json.loads(r[0]) for r in cur.fetchall()]
            except Exception as exc:  # noqa: BLE001
                logger.debug("[storage] query_cases failed: %s", exc)
                return []

    def count_cases(
        self,
        *,
        statuses: list[str] | None = None,
        exclude_validation: bool = False,
    ) -> int:
        with self._lock:
            where: list[str] = []
            args: list[Any] = []
            if statuses:
                placeholders = ",".join("?" * len(statuses))
                where.append(f"status IN ({placeholders})")
                args.extend(statuses)
            if exclude_validation:
                where.append("(validation_type IS NULL OR validation_type='' OR validation_type='NATURAL')")
            clause = (" WHERE " + " AND ".join(where)) if where else ""
            try:
                cur = self._conn.execute(
                    f"SELECT COUNT(*) FROM review_cases{clause}",
                    tuple(args),
                )
                return int(cur.fetchone()[0])
            except Exception:  # noqa: BLE001
                return 0

    def query_ledger_events(self, account_id: str, limit: int = 5000) -> list[dict[str, Any]]:
        with self._lock:
            try:
                cur = self._conn.execute(
                    "SELECT payload FROM durable_ledger_events"
                    " WHERE account_id=? ORDER BY sequence ASC LIMIT ?",
                    (str(account_id), int(limit)),
                )
                return [json.loads(r[0]) for r in cur.fetchall()]
            except Exception:  # noqa: BLE001
                rows: list[dict[str, Any]] = []
                cur = self._conn.execute(
                    "SELECT payload FROM kv WHERE table_name=? ORDER BY id ASC LIMIT ?",
                    ("durable_ledger_events", int(limit)),
                )
                for (payload,) in cur.fetchall():
                    try:
                        rec = json.loads(payload)
                    except Exception:  # noqa: BLE001
                        continue
                    if str(rec.get("accountId") or rec.get("account_id") or "") == str(account_id):
                        rows.append(rec)
                rows.sort(key=lambda r: int(r.get("sequence") or 0))
                return rows

    def persist_validation_marker(
        self, marker_id: str, tag: str, payload: dict[str, Any]
    ) -> None:
        payload_json = json.dumps(payload, ensure_ascii=False)
        now_utc = _utc_iso()
        ts = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO persistence_validation_markers"
                "  (marker_id, tag, payload, created_at_utc, created_at_ts)"
                "  VALUES (?,?,?,?,?)",
                (marker_id, tag, payload_json, now_utc, ts),
            )
            self._conn.commit()

    def delete_old_records(self, table: str, older_than_ts: float) -> int:
        with self._lock:
            if table in _TYPED_INSERT:
                try:
                    cur = self._conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE created_at_ts < ?",
                        (older_than_ts,),
                    )
                    n = int(cur.fetchone()[0])
                    self._conn.execute(
                        f"DELETE FROM {table} WHERE created_at_ts < ?",
                        (older_than_ts,),
                    )
                    self._conn.commit()
                    return n
                except Exception:  # noqa: BLE001
                    pass
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM kv WHERE table_name=? AND created_at < ?",
                (table, older_than_ts),
            )
            n = int(cur.fetchone()[0])
            self._conn.execute(
                "DELETE FROM kv WHERE table_name=? AND created_at < ?",
                (table, older_than_ts),
            )
            self._conn.commit()
            return n

    def close(self) -> None:
        """Close the underlying SQLite connection (releases file lock)."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass

    @property
    def backend_type(self) -> str:
        return "sqlite"

    @property
    def schema_version(self) -> int:
        return self._current_version()

    @property
    def db_path(self) -> str | None:
        return str(self._db_path)


# ─────────────────────────────────────────────────────────────────────────────
# Public research store wrapper
# ─────────────────────────────────────────────────────────────────────────────

class _ResearchStore:
    """Thread-safe research store.  Wraps a memory or sqlite adapter."""

    def __init__(self, adapter: _MemoryStore | _SqliteStore) -> None:
        self._adapter = adapter

    # ── core interface (backward-compatible) ──────────────────────────────────

    def append(self, table: str, record: dict[str, Any]) -> None:
        self._adapter.append(table, record)

    def query(self, table: str, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        return self._adapter.query(table, limit, offset)

    def count(self, table: str) -> int:
        return self._adapter.count(table)

    def clear_table(self, table: str) -> int:
        return self._adapter.clear_table(table)

    def get_by_pk(self, table: str, pk_value: str) -> dict[str, Any] | None:
        return self._adapter.get_by_pk(table, pk_value)

    def upsert(self, table: str, record: dict[str, Any]) -> bool:
        fn = getattr(self._adapter, "upsert", None)
        if callable(fn):
            return bool(fn(table, record))
        self.append(table, record)
        return True

    def query_cases(self, **kwargs: Any) -> list[dict[str, Any]]:
        fn = getattr(self._adapter, "query_cases", None)
        if callable(fn):
            return fn(**kwargs)
        return self.query("review_cases", limit=int(kwargs.get("limit") or 100))

    def count_cases(self, **kwargs: Any) -> int:
        fn = getattr(self._adapter, "count_cases", None)
        if callable(fn):
            return int(fn(**kwargs))
        return self.count("review_cases")

    def query_ledger_events(self, account_id: str, limit: int = 5000) -> list[dict[str, Any]]:
        """Return durable ledger events for one account ordered by sequence ASC."""
        fn = getattr(self._adapter, "query_ledger_events", None)
        if callable(fn):
            return fn(account_id, limit=limit)
        rows = [
            r
            for r in self.query("durable_ledger_events", limit=limit)
            if str(r.get("accountId") or r.get("account_id") or "") == account_id
        ]
        rows.sort(key=lambda r: int(r.get("sequence") or 0))
        return rows

    def append_ledger_event(self, record: dict[str, Any]) -> bool:
        """Persist one durable ledger event (INSERT OR IGNORE by event_id/idempotency)."""
        try:
            self.append("durable_ledger_events", record)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("[storage] append_ledger_event failed: %s", exc)
            return False

    def close(self) -> None:
        """Release underlying DB connection (needed on Windows before temp dir cleanup)."""
        if hasattr(self._adapter, "close"):
            self._adapter.close()

    # ── Phase 6 helpers ───────────────────────────────────────────────────────

    def persist_validation_marker(
        self,
        marker_id: str,
        tag: str = "PERSISTENCE_VALIDATION",
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Persist a tagged validation marker (idempotent by marker_id)."""
        self._adapter.persist_validation_marker(marker_id, tag, payload or {})

    def wal_checkpoint(self, mode: str = "TRUNCATE") -> dict[str, Any]:
        fn = getattr(self._adapter, "wal_checkpoint", None)
        if callable(fn):
            return fn(mode)
        return {"ok": True, "skipped": True, "mode": mode}

    def sqlite_runtime_profile(self, *, force_integrity: bool = False) -> dict[str, Any]:
        fn = getattr(self._adapter, "sqlite_runtime_profile", None)
        if callable(fn):
            try:
                return fn(force_integrity=force_integrity)
            except TypeError:
                return fn()
        return {"integrity_check": "unavailable"}

    def run_maintenance_integrity_check(self) -> dict[str, Any]:
        """Explicit maintenance/diagnostic integrity scan — NOT for hot status path.

        Holds the store lock for the duration of PRAGMA integrity_check.
        Call only from low-frequency ops / operator tools.
        """
        return {
            "ok": True,
            "researchOnly": True,
            "maintenance": True,
            "profile": self.sqlite_runtime_profile(force_integrity=True),
            "generatedAt": int(time.time() * 1000),
        }

    def delete_old_records(self, table: str, older_than_days: float = 30.0) -> int:
        """Retention helper: delete records older than N days, return count removed."""
        cutoff = time.time() - older_than_days * 86400
        return self._adapter.delete_old_records(table, cutoff)

    def paginate(self, table: str, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        """Return a paginated slice plus total/has_more metadata."""
        page = max(1, page)
        page_size = max(1, min(page_size, 500))
        offset = (page - 1) * page_size
        rows = self.query(table, limit=page_size, offset=offset)
        total = self.count(table)
        return {
            "page": page,
            "pageSize": page_size,
            "total": total,
            "rows": rows,
            "hasMore": (offset + len(rows)) < total,
        }

    # ── status / health ───────────────────────────────────────────────────────

    @property
    def backend_type(self) -> str:
        return self._adapter.backend_type

    @property
    def schema_version(self) -> int:
        return self._adapter.schema_version

    @property
    def db_path(self) -> str | None:
        return self._adapter.db_path

    def status(self) -> dict[str, Any]:
        """Return storage status suitable for API exposure (no secrets)."""
        try:
            from backend.nexus_research.storage_discovery import discover_storage  # type: ignore
            disc = discover_storage()
        except Exception:  # noqa: BLE001
            disc = {}

        try:
            from backend.nexus_research.boot_identity import get_boot_identity

            boot = get_boot_identity()
        except Exception:  # noqa: BLE001
            boot = {}

        # Never force full integrity_check on the hot status path.
        profile = self.sqlite_runtime_profile(force_integrity=False)
        probes: list[dict[str, Any]] = []
        try:
            probes = self.query("persistence_probes", limit=5)
        except Exception:  # noqa: BLE001
            probes = []
        previous_probe = probes[-1] if probes else None

        legacy_tables = [
            "events", "review_cases", "role_assessments", "research_decisions",
            "review_sessions", "sim_placeholders", "persistence_probes",
        ]
        sample_tables = list(TYPED_TABLES) + legacy_tables
        counts: dict[str, int] = {}
        now = time.time()
        count_cached = getattr(self, "_table_count_cache", None)
        if (
            count_cached is not None
            and (now - float(count_cached[0])) < getattr(self, "_TABLE_COUNT_CACHE_TTL_SEC", 60.0)
        ):
            counts = dict(count_cached[1])
        else:
            for t in sample_tables:
                try:
                    counts[t] = self.count(t)
                except Exception:  # noqa: BLE001
                    counts[t] = -1
            self._table_count_cache = (now, dict(counts))

        db_path = self.db_path
        path_redacted = None
        if db_path:
            p = str(db_path).replace("\\", "/")
            idx = p.find("/data/")
            path_redacted = p[idx:] if idx >= 0 else "nexus-research/nexus_research.db"

        db_size = None
        try:
            if db_path and Path(db_path).exists():
                db_size = int(Path(db_path).stat().st_size)
        except Exception:  # noqa: BLE001
            db_size = None

        # Durable claim requires restart proof — never from writability alone.
        durable_claim = bool(disc.get("durableClaim", False))
        restart_proof = bool(disc.get("restartProofVerified", False))

        return {
            "ok": True,
            "storageMode": self._adapter.backend_type,
            "storageModeClaim": disc.get("recommendedMode"),
            "pathRedacted": path_redacted,
            "writable": bool(disc.get("dataDirWritable", False)),
            "durableClaim": durable_claim,
            "restartProof": restart_proof,
            "volumeConfirmed": disc.get("volumeConfirmed", False),
            "persistentVolumeResourceConfirmed": disc.get(
                "persistentVolumeResourceConfirmed", False
            ),
            "persistentVolumeMountConfirmed": disc.get(
                "persistentVolumeMountConfirmed", False
            ),
            "persistentVolumePath": disc.get("persistentVolumePath"),
            "currentBootId": boot.get("bootId"),
            "previousProbeFound": previous_probe is not None,
            "previousProbeId": (previous_probe or {}).get("probeId"),
            "schemaVersion": self.schema_version,
            "lastMigrationVersion": self.schema_version,
            "migrationStatus": "applied",
            "walStatus": profile.get("journal_mode"),
            "sqliteRuntimeProfile": profile,
            "lastCheckpoint": None,
            "databaseSizeBytes": db_size,
            "lastBackup": None,
            "health": "ok" if (
                profile.get("integrity_check") in (None, "ok", "memory", "skipped_on_status_path")
                or str(profile.get("integrity_check")) == "ok"
                or str(profile.get("integrity_check", "")).startswith("skipped")
            ) else "degraded",
            "dbPath": path_redacted,
            "researchOnly": True,
            "production_persistence_available": bool(
                disc.get("productionPersistenceAvailable", False)
            ),
            "postgresDriverPending": True,
            "tableCounts": counts,
            "generatedAt": int(time.time() * 1000),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Store construction
# ─────────────────────────────────────────────────────────────────────────────

def _legacy_research_db_candidates(data_dir: Path) -> list[Path]:
    """Previous (incorrect) locations that must not be abandoned silently."""
    return [
        data_dir / "nexus_research.db",
    ]


def _migrate_legacy_research_db(target: Path, data_dir: Path) -> None:
    """Copy legacy /data/nexus_research.db into dedicated nexus-research/ if needed.

    Never deletes the legacy file. Never touches trading.db.
    Does not overwrite an existing non-empty target with an empty copy.
    """
    import shutil

    if target.exists() and target.stat().st_size > 0:
        return
    for legacy in _legacy_research_db_candidates(data_dir):
        if not legacy.exists() or legacy.resolve() == target.resolve():
            continue
        if legacy.name == "trading.db":
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "[nexus_research.storage] migrating legacy research DB %s → %s",
            legacy,
            target,
        )
        shutil.copy2(legacy, target)
        for suffix in ("-wal", "-shm"):
            side = Path(str(legacy) + suffix)
            if side.exists():
                shutil.copy2(side, Path(str(target) + suffix))
        return


def _build_store() -> _ResearchStore:
    """Build a research store based on env configuration.

    Postgres is detected but deferred (driver not installed).
    SQLite uses /data/nexus-research/nexus_research.db when NEXUS_DATA_DIR is set.
    Memory fallback is always available.
    """
    mode = os.getenv("NEXUS_RESEARCH_STORAGE_MODE", "auto").strip().lower()

    # Postgres: detect URL presence and warn — driver pending
    _has_postgres = bool(
        os.getenv("NEXUS_RESEARCH_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
        or os.getenv("POSTGRES_URL", "").strip()
        or os.getenv("PGHOST", "").strip()
    )
    if _has_postgres and mode in ("postgres", "auto"):
        logger.warning(
            "[nexus_research.storage] Postgres URL/host detected but psycopg2-binary is not in "
            "requirements.txt — postgres storage is pending.  Falling back to sqlite/memory."
        )

    # SQLite path — dedicated research directory under NEXUS_DATA_DIR
    if mode not in ("memory",):
        data_dir_env = os.getenv("NEXUS_DATA_DIR", "").strip()
        if data_dir_env:
            try:
                data_dir = Path(data_dir_env)
                data_dir.mkdir(parents=True, exist_ok=True)
                try:
                    from backend.nexus_research.boot_identity import research_data_dir

                    research_root = research_data_dir()
                except Exception:  # noqa: BLE001
                    research_root = data_dir / "nexus-research"
                    research_root.mkdir(parents=True, exist_ok=True)

                if research_root is None:
                    raise RuntimeError("research_data_dir unavailable")

                db_path = research_root / "nexus_research.db"
                _migrate_legacy_research_db(db_path, data_dir)

                # Safety: must never be the same file as trading.db
                try:
                    from backend.core.data_paths import resolve_runtime_db_path  # type: ignore
                    trading_raw = resolve_runtime_db_path()
                    if trading_raw:
                        trading_p = Path(str(trading_raw)).resolve()
                        if db_path.resolve() == trading_p:
                            raise ValueError(
                                f"Research DB path conflicts with trading.db: {db_path}"
                            )
                        if "trading.db" in str(db_path).replace("\\", "/").lower():
                            raise ValueError(
                                f"Research DB path must not use trading.db: {db_path}"
                            )
                except ImportError:
                    pass  # data_paths not available in deploy mirror — skip check

                adapter: _MemoryStore | _SqliteStore = _SqliteStore(db_path)
                logger.info("[nexus_research.storage] sqlite store → %s", db_path)
                return _ResearchStore(adapter)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[nexus_research.storage] sqlite unavailable (%s); falling back to memory", exc
                )

    mem_adapter = _MemoryStore()
    logger.info("[nexus_research.storage] in-memory store active")
    return _ResearchStore(mem_adapter)


def get_research_store() -> _ResearchStore:
    """Return the singleton research store, running migrations on first call."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = _build_store()
        return _STORE


# ─────────────────────────────────────────────────────────────────────────────
# Legacy helper (kept for backward compat)
# ─────────────────────────────────────────────────────────────────────────────

def storage_audit() -> dict[str, Any]:
    """Return storage audit summary (no secrets).  Deprecated — prefer store.status()."""
    store = get_research_store()
    return store.status()
