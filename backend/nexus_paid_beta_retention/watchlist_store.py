"""Server-authoritative watchlist store (in-memory staging; no fake accounts)."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from backend.nexus_paid_beta_retention.constants import WATCHLIST_LIMIT


def _utcnow_ms() -> int:
    return int(time.time() * 1000)


class WatchlistStore:
    """Per-account watchlist. Canonical only when account_id is real."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_account: dict[str, dict[str, Any]] = {}

    def list_items(self, account_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._by_account.get(account_id) or {
                "account_id": account_id,
                "items": [],
                "updated_at": None,
            }
            return {
                "account_id": account_id,
                "items": list(state["items"]),
                "updated_at": state.get("updated_at"),
                "limit": WATCHLIST_LIMIT,
                "authority": "SERVER",
                "canonical": True,
            }

    def add(
        self,
        account_id: str,
        symbol: str,
        *,
        asset_class: str = "CRYPTO",
    ) -> dict[str, Any]:
        sym = str(symbol or "").upper().strip()
        if not sym:
            raise ValueError("symbol_required")
        ac = str(asset_class or "CRYPTO").upper()
        with self._lock:
            state = self._by_account.setdefault(
                account_id,
                {"account_id": account_id, "items": [], "updated_at": None},
            )
            items: list[dict[str, Any]] = state["items"]
            if any(i["symbol"] == sym and i["asset_class"] == ac for i in items):
                return self.list_items(account_id)
            items.insert(
                0,
                {
                    "symbol": sym,
                    "asset_class": ac,
                    "added_at": _utcnow_ms(),
                },
            )
            state["items"] = items[:WATCHLIST_LIMIT]
            state["updated_at"] = _utcnow_ms()
            return self.list_items(account_id)

    def remove(self, account_id: str, symbol: str, *, asset_class: str = "CRYPTO") -> dict[str, Any]:
        sym = str(symbol or "").upper().strip()
        ac = str(asset_class or "CRYPTO").upper()
        with self._lock:
            state = self._by_account.setdefault(
                account_id,
                {"account_id": account_id, "items": [], "updated_at": None},
            )
            state["items"] = [
                i
                for i in state["items"]
                if not (i["symbol"] == sym and i["asset_class"] == ac)
            ]
            state["updated_at"] = _utcnow_ms()
            return self.list_items(account_id)


_STORE: Optional[WatchlistStore] = None
_STORE_LOCK = threading.Lock()


def get_watchlist_store() -> WatchlistStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = WatchlistStore()
        return _STORE
