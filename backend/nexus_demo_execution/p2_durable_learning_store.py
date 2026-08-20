"""Durable P2 research lesson store. PostgreSQL in production; SQLite file for restart tests."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS p2_research_lessons (
    lesson_id TEXT PRIMARY KEY,
    source_trade_id TEXT NOT NULL,
    source_decision_id TEXT NOT NULL,
    source_evidence_hash TEXT NOT NULL UNIQUE,
    campaign_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    mistake_labels TEXT NOT NULL DEFAULT '[]',
    primary_mistake TEXT NOT NULL,
    lesson_rule TEXT NOT NULL,
    support_count INTEGER NOT NULL DEFAULT 1,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'candidate_only',
    policy_truth INTEGER NOT NULL DEFAULT 0,
    revalidation_required INTEGER NOT NULL DEFAULT 1,
    ttl_trades INTEGER,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _labels(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            return [value]
    return []


def _row_to_lesson(row: dict[str, Any]) -> dict[str, Any]:
    labels = row.get("mistake_labels")
    if isinstance(labels, str):
        labels = _labels(labels)
    payload = row.get("payload_json") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    policy = row.get("policy_truth")
    revalidate = row.get("revalidation_required")
    return {
        "lesson_id": row.get("lesson_id"),
        "source_trade_id": row.get("source_trade_id"),
        "source_decision_id": row.get("source_decision_id"),
        "source_evidence_hash": row.get("source_evidence_hash"),
        "campaign_id": row.get("campaign_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "mistake_labels": labels,
        "primary_mistake": row.get("primary_mistake"),
        "lesson_rule": row.get("lesson_rule"),
        "support_count": int(row.get("support_count") or 1),
        "confidence": row.get("confidence"),
        "status": row.get("status") or "candidate_only",
        "policy_truth": bool(policy) if policy not in (None, "") else False,
        "revalidation_required": bool(revalidate) if revalidate not in (None, "") else True,
        "ttl_trades": row.get("ttl_trades"),
        "expires_at": row.get("expires_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "payload": payload,
    }


class DurableLessonStore:
    """Process-exit durable store. Never a live execution veto."""

    def __init__(self, *, sqlite_path: str | Path | None = None, pool: Any | None = None) -> None:
        if pool is None and sqlite_path is None:
            raise ValueError("durable_lesson_store_backend_required")
        self.pool = pool
        self.sqlite_path = Path(sqlite_path) if sqlite_path is not None else None
        self._sqlite: sqlite3.Connection | None = None
        if self.sqlite_path is not None:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._sqlite = sqlite3.connect(str(self.sqlite_path))
            self._sqlite.row_factory = sqlite3.Row
            self._sqlite.execute(SQLITE_DDL)
            self._sqlite.commit()

    def close(self) -> None:
        if self._sqlite is not None:
            self._sqlite.close()
            self._sqlite = None

    def upsert_lesson(self, lesson: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_by_evidence_hash(str(lesson.get("source_evidence_hash") or ""))
        now = _now()
        if existing:
            existing["updated_at"] = now
            existing["payload"] = lesson.get("payload") or existing.get("payload") or {}
            self._write(existing, insert=False)
            return existing
        support = int(lesson.get("support_count") or 1)
        policy = bool(lesson.get("policy_truth"))
        if policy and support < 3:
            policy = False
        row = {
            "lesson_id": lesson["lesson_id"],
            "source_trade_id": lesson["source_trade_id"],
            "source_decision_id": lesson["source_decision_id"],
            "source_evidence_hash": lesson["source_evidence_hash"],
            "campaign_id": lesson["campaign_id"],
            "symbol": lesson["symbol"],
            "side": lesson["side"],
            "mistake_labels": list(lesson.get("mistake_labels") or lesson.get("labels") or []),
            "primary_mistake": lesson["primary_mistake"],
            "lesson_rule": lesson.get("lesson_rule") or lesson.get("rule") or "",
            "support_count": support,
            "confidence": lesson.get("confidence"),
            "status": lesson.get("status") or "candidate_only",
            "policy_truth": policy,
            "revalidation_required": bool(lesson.get("revalidation_required", True)),
            "ttl_trades": lesson.get("ttl_trades"),
            "expires_at": lesson.get("expires_at"),
            "created_at": now,
            "updated_at": now,
            "payload": lesson.get("payload") or lesson,
        }
        self._write(row, insert=True)
        return row

    def get_by_evidence_hash(self, source_evidence_hash: str) -> dict[str, Any] | None:
        if not source_evidence_hash:
            return None
        if self._sqlite is not None:
            cur = self._sqlite.execute(
                "SELECT * FROM p2_research_lessons WHERE source_evidence_hash=?",
                (source_evidence_hash,),
            )
            found = cur.fetchone()
            return _row_to_lesson(dict(found)) if found else None
        rows = self.pool.fetchall(
            """
            SELECT lesson_id, source_trade_id, source_decision_id, source_evidence_hash, campaign_id,
                   symbol, side, mistake_labels, primary_mistake, lesson_rule, support_count, confidence,
                   status, policy_truth, revalidation_required, ttl_trades, expires_at, created_at,
                   updated_at, payload_json
            FROM nexus.p2_research_lessons
            WHERE source_evidence_hash=%s
            """,
            (source_evidence_hash,),
        )
        if not rows:
            return None
        return self._pg_row(rows[0])

    def list_lessons(self) -> list[dict[str, Any]]:
        if self._sqlite is not None:
            cur = self._sqlite.execute("SELECT * FROM p2_research_lessons")
            return [_row_to_lesson(dict(item)) for item in cur.fetchall()]
        rows = self.pool.fetchall(
            """
            SELECT lesson_id, source_trade_id, source_decision_id, source_evidence_hash, campaign_id,
                   symbol, side, mistake_labels, primary_mistake, lesson_rule, support_count, confidence,
                   status, policy_truth, revalidation_required, ttl_trades, expires_at, created_at,
                   updated_at, payload_json
            FROM nexus.p2_research_lessons
            """
        )
        return [self._pg_row(row) for row in rows]

    def _write(self, row: dict[str, Any], *, insert: bool) -> None:
        labels = json.dumps(row.get("mistake_labels") or [])
        payload = json.dumps(row.get("payload") or {}, default=str)
        if self._sqlite is not None:
            if insert:
                self._sqlite.execute(
                    """
                    INSERT INTO p2_research_lessons (
                        lesson_id, source_trade_id, source_decision_id, source_evidence_hash, campaign_id,
                        symbol, side, mistake_labels, primary_mistake, lesson_rule, support_count, confidence,
                        status, policy_truth, revalidation_required, ttl_trades, expires_at, created_at,
                        updated_at, payload_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        row["lesson_id"],
                        row["source_trade_id"],
                        row["source_decision_id"],
                        row["source_evidence_hash"],
                        row["campaign_id"],
                        row["symbol"],
                        row["side"],
                        labels,
                        row["primary_mistake"],
                        row["lesson_rule"],
                        row["support_count"],
                        row.get("confidence"),
                        row["status"],
                        1 if row["policy_truth"] else 0,
                        1 if row["revalidation_required"] else 0,
                        row.get("ttl_trades"),
                        row.get("expires_at"),
                        row["created_at"],
                        row["updated_at"],
                        payload,
                    ),
                )
            else:
                self._sqlite.execute(
                    """
                    UPDATE p2_research_lessons
                    SET updated_at=?, payload_json=?
                    WHERE source_evidence_hash=?
                    """,
                    (row["updated_at"], payload, row["source_evidence_hash"]),
                )
            self._sqlite.commit()
            return
        if insert:
            self.pool.execute(
                """
                INSERT INTO nexus.p2_research_lessons (
                    lesson_id, source_trade_id, source_decision_id, source_evidence_hash, campaign_id,
                    symbol, side, mistake_labels, primary_mistake, lesson_rule, support_count, confidence,
                    status, policy_truth, revalidation_required, ttl_trades, expires_at, payload_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                """,
                (
                    row["lesson_id"],
                    row["source_trade_id"],
                    row["source_decision_id"],
                    row["source_evidence_hash"],
                    row["campaign_id"],
                    row["symbol"],
                    row["side"],
                    labels,
                    row["primary_mistake"],
                    row["lesson_rule"],
                    row["support_count"],
                    row.get("confidence"),
                    row["status"],
                    row["policy_truth"],
                    row["revalidation_required"],
                    row.get("ttl_trades"),
                    row.get("expires_at"),
                    payload,
                ),
            )
            return
        self.pool.execute(
            """
            UPDATE nexus.p2_research_lessons
            SET updated_at=NOW(), payload_json=%s::jsonb
            WHERE source_evidence_hash=%s
            """,
            (payload, row["source_evidence_hash"]),
        )

    def _pg_row(self, row: tuple[Any, ...]) -> dict[str, Any]:
        labels = row[7]
        if not isinstance(labels, list):
            labels = _labels(labels)
        payload = row[19] if len(row) > 19 else {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        return {
            "lesson_id": row[0],
            "source_trade_id": row[1],
            "source_decision_id": row[2],
            "source_evidence_hash": row[3],
            "campaign_id": row[4],
            "symbol": row[5],
            "side": row[6],
            "mistake_labels": labels,
            "primary_mistake": row[8],
            "lesson_rule": row[9],
            "support_count": int(row[10] or 1),
            "confidence": row[11],
            "status": row[12],
            "policy_truth": bool(row[13]),
            "revalidation_required": bool(row[14]),
            "ttl_trades": row[15],
            "expires_at": row[16].isoformat() if getattr(row[16], "isoformat", None) else row[16],
            "created_at": row[17].isoformat() if getattr(row[17], "isoformat", None) else row[17],
            "updated_at": row[18].isoformat() if getattr(row[18], "isoformat", None) else row[18],
            "payload": payload or {},
        }
