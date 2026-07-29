"""Account epoch tracking — detect fund reset while retaining historical data."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_demo_execution.account_reader import DemoAccountSnapshot


def _epoch_fingerprint(snap: DemoAccountSnapshot) -> str:
    payload = (
        f"{snap.wallet_balance:.4f}|{snap.equity:.4f}|"
        f"{len(snap.open_positions)}|{len(snap.open_orders)}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class AccountEpoch:
    epoch_id: str
    started_at: float
    fingerprint: str
    wallet_balance: float
    retained_trade_count: int = 0
    retained_reflection_count: int = 0
    superseded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch_id": self.epoch_id,
            "started_at": self.started_at,
            "fingerprint": self.fingerprint,
            "wallet_balance": self.wallet_balance,
            "retained_trade_count": self.retained_trade_count,
            "retained_reflection_count": self.retained_reflection_count,
            "superseded": self.superseded,
        }


@dataclass
class AccountEpochTracker:
    """Detects fund reset (large balance jump with flat book) → new epoch."""

    reset_threshold_pct: float = 0.50
    reset_min_delta: float = 100.0
    epochs: list[AccountEpoch] = field(default_factory=list)
    _epoch_seq: int = 0

    @property
    def current_epoch(self) -> AccountEpoch | None:
        if not self.epochs:
            return None
        for ep in reversed(self.epochs):
            if not ep.superseded:
                return ep
        return self.epochs[-1]

    def observe(
        self,
        snap: DemoAccountSnapshot,
        *,
        trade_count: int = 0,
        reflection_count: int = 0,
    ) -> AccountEpoch:
        fp = _epoch_fingerprint(snap)
        current = self.current_epoch
        if current is None:
            return self._start_epoch(snap, fp, trade_count, reflection_count)

        if self._is_fund_reset(current, snap):
            current.superseded = True
            current.retained_trade_count = trade_count
            current.retained_reflection_count = reflection_count
            return self._start_epoch(snap, fp, 0, 0)

        current.fingerprint = fp
        current.wallet_balance = snap.wallet_balance
        return current

    def _start_epoch(
        self,
        snap: DemoAccountSnapshot,
        fingerprint: str,
        trade_count: int,
        reflection_count: int,
    ) -> AccountEpoch:
        self._epoch_seq += 1
        ep = AccountEpoch(
            epoch_id=f"epoch-{self._epoch_seq:04d}",
            started_at=time.time(),
            fingerprint=fingerprint,
            wallet_balance=snap.wallet_balance,
            retained_trade_count=trade_count,
            retained_reflection_count=reflection_count,
        )
        self.epochs.append(ep)
        return ep

    def _is_fund_reset(self, current: AccountEpoch, snap: DemoAccountSnapshot) -> bool:
        prev = current.wallet_balance
        if prev <= 0:
            return False
        delta = snap.wallet_balance - prev
        if delta < self.reset_min_delta:
            return False
        pct = delta / prev
        flat_book = len(snap.open_positions) == 0 and len(snap.open_orders) == 0
        return pct >= self.reset_threshold_pct and flat_book

    def summary(self) -> dict[str, Any]:
        cur = self.current_epoch
        return {
            "epoch_count": len(self.epochs),
            "current_epoch_id": cur.epoch_id if cur else None,
            "epochs": [e.to_dict() for e in self.epochs],
        }
