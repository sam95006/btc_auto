"""Bounded psycopg connection pool lifecycle."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_persistence_pg.env import assert_pg_environment_allowed

logger = logging.getLogger(__name__)


@dataclass
class PostgresPool:
    """Optional psycopg pool — never auto-wired into live Shadow conductor."""

    database_url: str
    min_size: int = 1
    max_size: int = 5
    max_reconnect_attempts: int = 3
    reconnect_backoff_sec: float = 0.5
    _pool: Any = field(default=None, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def open(self) -> None:
        assert_pg_environment_allowed()
        if self._pool is not None:
            return
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError("psycopg_pool_not_installed") from exc
        self._pool = ConnectionPool(
            conninfo=self.database_url,
            min_size=self.min_size,
            max_size=self.max_size,
            kwargs={"options": "-c timezone=UTC"},
            open=True,
        )

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None
        self._closed = True

    def connection(self):
        if self._closed:
            raise RuntimeError("pool_closed")
        if self._pool is None:
            self.open()
        return self._pool.connection()

    def apply_migration(
        self,
        sql: str,
        *,
        version: str,
        checksum_sha256: str,
        description: str,
    ) -> None:
        """Apply one migration file and history row in a single transaction."""
        last_error: Exception | None = None
        for attempt in range(1, self.max_reconnect_attempts + 1):
            try:
                with self.connection() as conn:
                    with conn.transaction():
                        with conn.cursor() as cur:
                            cur.execute(sql)
                            cur.execute(
                                """
                                INSERT INTO nexus.schema_migrations
                                  (version, checksum_sha256, description)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (version) DO NOTHING
                                """,
                                (version, checksum_sha256, description),
                            )
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "postgres_migration_retry attempt=%s error=%s",
                    attempt,
                    exc,
                )
                if attempt < self.max_reconnect_attempts:
                    time.sleep(self.reconnect_backoff_sec * attempt)
        raise RuntimeError(f"postgres_migration_failed:{last_error}") from last_error

    def execute(self, statement: str, params: tuple[Any, ...] = ()) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self.max_reconnect_attempts + 1):
            try:
                with self.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(statement, params)
                    conn.commit()
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "postgres_execute_retry attempt=%s error=%s",
                    attempt,
                    exc,
                )
                if attempt < self.max_reconnect_attempts:
                    time.sleep(self.reconnect_backoff_sec * attempt)
        raise RuntimeError(f"postgres_execute_failed:{last_error}") from last_error

    def fetchval(self, statement: str, params: tuple[Any, ...] = ()) -> Any:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(statement, params)
                row = cur.fetchone()
            conn.commit()
        return row[0] if row else None

    def fetchall(self, statement: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(statement, params)
                rows = cur.fetchall()
            conn.commit()
        return list(rows)

    def readiness(self) -> dict[str, Any]:
        if self._closed:
            return {"ready": False, "reason": "pool_closed"}
        try:
            val = self.fetchval("SELECT 1")
            return {"ready": val == 1, "reason": None if val == 1 else "unexpected_select"}
        except Exception as exc:  # noqa: BLE001
            return {"ready": False, "reason": str(exc)}
