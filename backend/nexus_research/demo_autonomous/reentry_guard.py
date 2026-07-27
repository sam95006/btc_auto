"""Prevent immediate re-entry on same symbol/side/strategy without fresh signal."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class ClosedTradeFingerprint:
    symbol: str
    side: str
    strategy: str
    signal_id: str
    closed_at_ms: int


class ReentryGuard:
    """Block same setup until new market snapshot + new signal id."""

    def __init__(self, *, min_cooldown_ms: int = 60_000) -> None:
        self.min_cooldown_ms = min_cooldown_ms
        self._last: ClosedTradeFingerprint | None = None
        self._lock = threading.Lock()

    def record_close(
        self,
        *,
        symbol: str,
        side: str,
        strategy: str,
        signal_id: str = "",
        closed_at_ms: int | None = None,
    ) -> None:
        with self._lock:
            self._last = ClosedTradeFingerprint(
                symbol=symbol.upper(),
                side=side,
                strategy=strategy,
                signal_id=str(signal_id or ""),
                closed_at_ms=closed_at_ms or int(time.time() * 1000),
            )

    def allow(
        self,
        *,
        symbol: str,
        side: str,
        strategy: str,
        signal_id: str = "",
        market_snapshot_id: str = "",
        now_ms: int | None = None,
    ) -> tuple[bool, str | None]:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        with self._lock:
            last = self._last
        if last is None:
            return True, None
        if (
            last.symbol == symbol.upper()
            and last.side == side
            and last.strategy == strategy
        ):
            if now - last.closed_at_ms < self.min_cooldown_ms:
                return False, "reentry_cooldown"
            # Same setup requires a new signal id (not blank-equal) and snapshot id present.
            if signal_id and last.signal_id and signal_id == last.signal_id:
                return False, "same_signal_id"
            if not market_snapshot_id:
                return False, "market_snapshot_required"
            if signal_id and last.signal_id and signal_id == last.signal_id:
                return False, "same_signal_id"
        return True, None

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            last = self._last
        if last is None:
            return {"lastClose": None}
        return {
            "lastClose": {
                "symbol": last.symbol,
                "side": last.side,
                "strategy": last.strategy,
                "signalId": last.signal_id,
                "closedAtMs": last.closed_at_ms,
            }
        }


_GUARD: ReentryGuard | None = None
_G_LOCK = threading.Lock()


def get_reentry_guard() -> ReentryGuard:
    global _GUARD
    with _G_LOCK:
        if _GUARD is None:
            _GUARD = ReentryGuard()
        return _GUARD
