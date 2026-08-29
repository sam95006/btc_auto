"""Personal watchlist persistence (PERSONAL-1).

Reuses the existing member watchlist tables (nexus.watchlists /
nexus.watchlist_items from migration 0003) rather than creating a parallel
store. Capacity is enforced by the service against the effective plan's
watchlist_items quota — not by a hard-coded limit here.
"""

from __future__ import annotations

import uuid
from typing import Optional

from backend.nexus_persistence_pg.pool import PostgresPool


def _norm(symbol: str) -> str:
    return (symbol or "").strip().upper()


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

    def _watchlist_id(self, account_id: str) -> str:
        rows = self.pool.fetchall(
            "SELECT watchlist_id FROM nexus.watchlists WHERE account_id=%s AND archived_at IS NULL LIMIT 1",
            (account_id,),
        )
        if rows:
            return rows[0][0]
        watchlist_id = f"wl_{uuid.uuid4().hex[:16]}"
        self.pool.execute(
            "INSERT INTO nexus.watchlists (watchlist_id, account_id) VALUES (%s, %s)",
            (watchlist_id, account_id),
        )
        return watchlist_id

    def add_symbol(self, account_id: str, symbol: str) -> None:
        watchlist_id = self._watchlist_id(account_id)
        self.pool.execute(
            "INSERT INTO nexus.watchlist_items (watchlist_id, symbol) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (watchlist_id, _norm(symbol)),
        )

    def remove_symbol(self, account_id: str, symbol: str) -> None:
        self.pool.execute(
            """
            DELETE FROM nexus.watchlist_items wi
            USING nexus.watchlists w
            WHERE wi.watchlist_id = w.watchlist_id AND w.account_id = %s AND wi.symbol = %s
            """,
            (account_id, _norm(symbol)),
        )

    def contains(self, account_id: str, symbol: str) -> bool:
        return _norm(symbol) in {s.upper() for s in self.list_symbols(account_id)}
