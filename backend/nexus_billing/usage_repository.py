"""Durable, atomic usage metering (PostgreSQL) for BILLING-6.

Atomicity and idempotency are enforced by the database, not process memory:
  * Idempotency: UNIQUE(account_id, quota_code, idempotency_key) on usage_events.
    A duplicate request is a no-op that returns the current counter.
  * At-most-once effect within the limit: the consume runs in a single
    transaction. The counter increment is a guarded UPSERT that only applies when
    used + amount <= limit (both for a fresh insert and a conflict update). If it
    would exceed the limit, the transaction is rolled back (so the idempotency
    event is not persisted for a denied attempt) and the consume is denied.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from backend.nexus_persistence_pg.pool import PostgresPool


class UsageRepository:
    def __init__(self, pool: PostgresPool):
        self.pool = pool

    def get_used(self, account_id: str, quota_code: str, window_type: str, window_start: Optional[datetime]) -> int:
        if window_start is None:
            return 0
        rows = self.pool.fetchall(
            """
            SELECT used FROM nexus.usage_counters
            WHERE account_id = %s AND quota_code = %s AND window_type = %s AND window_start = %s
            LIMIT 1
            """,
            (account_id, quota_code, window_type, window_start),
        )
        return int(rows[0][0]) if rows else 0

    def consume(
        self,
        *,
        account_id: str,
        quota_code: str,
        window_type: str,
        window_start: datetime,
        amount: int,
        limit: int,
        idempotency_key: str,
    ) -> tuple[bool, int]:
        """Atomically consume ``amount`` against a limit. Returns (allowed, used).

        A duplicate idempotency_key returns (True, current_used) without
        incrementing. Exceeding the limit returns (False, current_used) and
        persists nothing.
        """
        if amount <= 0:
            raise ValueError("invalid_amount")

        class _Denied(Exception):
            def __init__(self, used: int) -> None:
                self.used = used

        usage_event_id = f"ue_{uuid.uuid4().hex[:16]}"
        try:
            with self.pool.connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO nexus.usage_events
                                (usage_event_id, account_id, quota_code, idempotency_key, amount, window_start)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (account_id, quota_code, window_start, idempotency_key) DO NOTHING
                            RETURNING usage_event_id
                            """,
                            (usage_event_id, account_id, quota_code, idempotency_key, amount, window_start),
                        )
                        claimed = cur.fetchone()
                        if not claimed:
                            # Duplicate request -> idempotent no-op.
                            cur.execute(
                                """
                                SELECT used FROM nexus.usage_counters
                                WHERE account_id=%s AND quota_code=%s AND window_type=%s AND window_start=%s
                                """,
                                (account_id, quota_code, window_type, window_start),
                            )
                            row = cur.fetchone()
                            return True, int(row[0]) if row else 0

                        # Guarded UPSERT: the fresh INSERT only fires when
                        # amount <= limit; the conflict UPDATE only when the new
                        # total stays within the limit.
                        cur.execute(
                            """
                            INSERT INTO nexus.usage_counters
                                (account_id, quota_code, window_type, window_start, used)
                            SELECT %s, %s, %s, %s, %s
                            WHERE %s <= %s
                            ON CONFLICT (account_id, quota_code, window_type, window_start)
                            DO UPDATE SET used = nexus.usage_counters.used + EXCLUDED.used,
                                          updated_at = NOW()
                            WHERE nexus.usage_counters.used + EXCLUDED.used <= %s
                            RETURNING used
                            """,
                            (account_id, quota_code, window_type, window_start, amount, amount, limit, limit),
                        )
                        row = cur.fetchone()
                        if row is None:
                            # Over the limit. Read current used, then roll back so
                            # the idempotency event is not kept for a denied call.
                            cur.execute(
                                """
                                SELECT used FROM nexus.usage_counters
                                WHERE account_id=%s AND quota_code=%s AND window_type=%s AND window_start=%s
                                """,
                                (account_id, quota_code, window_type, window_start),
                            )
                            cur_row = cur.fetchone()
                            raise _Denied(int(cur_row[0]) if cur_row else 0)
                        return True, int(row[0])
        except _Denied as denied:
            return False, denied.used
