"""Personal watchlist persistence (PERSONAL-1 + PERSONAL-2).

Reuses the existing member watchlist tables (nexus.watchlists /
nexus.watchlist_items from migration 0003) rather than creating a parallel
store.

PERSONAL-2 hardening:
- Capacity is enforced atomically inside a single DB transaction. The active
  watchlist row is locked `FOR UPDATE`, so a concurrent pair of adds is
  serialized and can never push the item count past the plan capacity.
- Single active watchlist per account is enforced durably by migration
  0014 (a partial unique index); the get-or-create path uses a deterministic
  watchlist id so concurrent first-inserts converge to one row.
- Account isolation: every read/write is scoped by account_id.
"""

from __future__ import annotations

from typing import Optional

from backend.nexus_persistence_pg.pool import PostgresPool

# Atomic add outcomes.
ADD_OK = "ADDED"
ADD_DUPLICATE = "DUPLICATE"
ADD_CAPACITY = "CAPACITY"


def _norm(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _deterministic_watchlist_id(account_id: str) -> str:
    # Deterministic per-account id so two concurrent first-time creates target
    # the same primary key and dedup via ON CONFLICT instead of creating a
    # second active watchlist.
    return f"wl_default_{account_id}"


class PersonalWatchlistRepository:
    def __init__(self, pool: PostgresPool):
        self.pool = pool

    def list_symbols(self, account_id: str) -> list[str]:
        rows = self.pool.fetchall(
            """
            SELECT wi.symbol
            FROM nexus.watchlists w
            JOIN nexus.watchlist_items wi ON wi.watchlist_id = w.watchlist_id
            WHERE w.account_id = %s AND w.archived_at IS NULL
            ORDER BY wi.added_at ASC
            """,
            (account_id,),
        )
        return [row[0] for row in rows]

    def count(self, account_id: str) -> int:
        return len(self.list_symbols(account_id))

    def contains(self, account_id: str, symbol: str) -> bool:
        return _norm(symbol) in {s.upper() for s in self.list_symbols(account_id)}

    def try_add_symbol(self, account_id: str, symbol: str, capacity: int) -> str:
        """Atomically add a symbol subject to `capacity`.

        Returns ADD_OK, ADD_DUPLICATE, or ADD_CAPACITY. The whole check-then-
        insert runs in one transaction with the account's active watchlist row
        locked FOR UPDATE, so concurrent adds cannot exceed capacity.
        """
        symbol = _norm(symbol)
        with self.pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    watchlist_id = self._locked_active_watchlist_id(cur, account_id)
                    cur.execute(
                        "SELECT 1 FROM nexus.watchlist_items WHERE watchlist_id=%s AND symbol=%s",
                        (watchlist_id, symbol),
                    )
                    if cur.fetchone():
                        return ADD_DUPLICATE
                    cur.execute(
                        "SELECT COUNT(*) FROM nexus.watchlist_items WHERE watchlist_id=%s",
                        (watchlist_id,),
                    )
                    current = int(cur.fetchone()[0])
                    if current >= max(0, int(capacity)):
                        return ADD_CAPACITY
                    cur.execute(
                        "INSERT INTO nexus.watchlist_items (watchlist_id, symbol) "
                        "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (watchlist_id, symbol),
                    )
                    return ADD_OK

    def _locked_active_watchlist_id(self, cur, account_id: str) -> str:
        cur.execute(
            "SELECT watchlist_id FROM nexus.watchlists "
            "WHERE account_id=%s AND archived_at IS NULL "
            "ORDER BY created_at ASC LIMIT 1 FOR UPDATE",
            (account_id,),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        watchlist_id = _deterministic_watchlist_id(account_id)
        cur.execute(
            "INSERT INTO nexus.watchlists (watchlist_id, account_id) "
            "VALUES (%s, %s) ON CONFLICT (watchlist_id) DO NOTHING",
            (watchlist_id, account_id),
        )
        cur.execute(
            "SELECT watchlist_id FROM nexus.watchlists "
            "WHERE account_id=%s AND archived_at IS NULL "
            "ORDER BY created_at ASC LIMIT 1 FOR UPDATE",
            (account_id,),
        )
        return cur.fetchone()[0]

    def remove_symbol(self, account_id: str, symbol: str) -> None:
        self.pool.execute(
            """
            DELETE FROM nexus.watchlist_items wi
            USING nexus.watchlists w
            WHERE wi.watchlist_id = w.watchlist_id AND w.account_id = %s AND wi.symbol = %s
            """,
            (account_id, _norm(symbol)),
        )

    def active_watchlist_count(self, account_id: str) -> int:
        """Number of non-archived watchlists for the account (should be <= 1)."""
        return int(
            self.pool.fetchval(
                "SELECT COUNT(*) FROM nexus.watchlists WHERE account_id=%s AND archived_at IS NULL",
                (account_id,),
            )
            or 0
        )
