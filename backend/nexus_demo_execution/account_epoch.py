"""Account epoch tracking — detect fund reset while retaining historical data."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.account_reader import DemoAccountSnapshot

_PERSIST_NAME = "account_epoch_state.json"


def _epoch_fingerprint(snap: DemoAccountSnapshot) -> str:
    payload = (
        f"{snap.wallet_balance:.4f}|{snap.equity:.4f}|"
        f"{len(snap.open_positions)}|{len(snap.open_orders)}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def runtime_demo_account_fingerprint(
    *,
    api_domain: str,
    account_created_at: str | None,
    wallet_snapshot_reference: str | None,
) -> str:
    """Hashed/redacted account identity — never raw secrets."""
    raw = f"{api_domain}|{account_created_at or ''}|{wallet_snapshot_reference or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass
class AccountEpoch:
    epoch_id: str
    started_at: float
    fingerprint: str
    wallet_balance: float
    retained_trade_count: int = 0
    retained_reflection_count: int = 0
    superseded: bool = False
    api_domain: str = "https://api-demo.bybit.com"
    account_created_at: str | None = None
    wallet_snapshot_reference: str | None = None
    runtime_demo_account_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch_id": self.epoch_id,
            "started_at": self.started_at,
            "fingerprint": self.fingerprint,
            "wallet_balance": self.wallet_balance,
            "retained_trade_count": self.retained_trade_count,
            "retained_reflection_count": self.retained_reflection_count,
            "superseded": self.superseded,
            "api_domain": self.api_domain,
            "account_created_at": self.account_created_at,
            "wallet_snapshot_reference": self.wallet_snapshot_reference,
            "runtime_demo_account_fingerprint": self.runtime_demo_account_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountEpoch":
        return cls(
            epoch_id=str(data.get("epoch_id") or "epoch-0001"),
            started_at=float(data.get("started_at") or time.time()),
            fingerprint=str(data.get("fingerprint") or ""),
            wallet_balance=float(data.get("wallet_balance") or 0.0),
            retained_trade_count=int(data.get("retained_trade_count") or 0),
            retained_reflection_count=int(data.get("retained_reflection_count") or 0),
            superseded=bool(data.get("superseded") or False),
            api_domain=str(data.get("api_domain") or "https://api-demo.bybit.com"),
            account_created_at=data.get("account_created_at"),
            wallet_snapshot_reference=data.get("wallet_snapshot_reference"),
            runtime_demo_account_fingerprint=str(data.get("runtime_demo_account_fingerprint") or ""),
        )


@dataclass
class AccountEpochTracker:
    """Detects fund reset (large balance jump with flat book) → new epoch.

    Persists across process restart. Restart alone must NOT create a new epoch.
    """

    reset_threshold_pct: float = 0.50
    reset_min_delta: float = 100.0
    epochs: list[AccountEpoch] = field(default_factory=list)
    _epoch_seq: int = 0
    api_domain: str = "https://api-demo.bybit.com"
    account_created_at: str | None = None
    _persist_path: Path | None = field(default=None, repr=False)

    @property
    def current_epoch(self) -> AccountEpoch | None:
        if not self.epochs:
            return None
        for ep in reversed(self.epochs):
            if not ep.superseded:
                return ep
        return self.epochs[-1]

    def attach_persist_path(self, data_root: Path) -> None:
        self._persist_path = Path(data_root) / "artifacts" / "demo_validation" / _PERSIST_NAME
        self.load(Path(data_root))

    def persist(self, data_root: Path | None = None) -> None:
        path = self._persist_path
        if data_root is not None:
            path = Path(data_root) / "artifacts" / "demo_validation" / _PERSIST_NAME
            self._persist_path = path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "epoch_seq": self._epoch_seq,
            "api_domain": self.api_domain,
            "account_created_at": self.account_created_at,
            "epochs": [e.to_dict() for e in self.epochs],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def load(self, data_root: Path) -> bool:
        path = Path(data_root) / "artifacts" / "demo_validation" / _PERSIST_NAME
        self._persist_path = path
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        self._epoch_seq = int(payload.get("epoch_seq") or 0)
        self.api_domain = str(payload.get("api_domain") or self.api_domain)
        self.account_created_at = payload.get("account_created_at")
        self.epochs = [AccountEpoch.from_dict(e) for e in (payload.get("epochs") or [])]
        return bool(self.epochs)

    def observe(
        self,
        snap: DemoAccountSnapshot,
        *,
        trade_count: int = 0,
        reflection_count: int = 0,
        persist: bool = True,
    ) -> AccountEpoch:
        fp = _epoch_fingerprint(snap)
        wallet_ref = f"wb:{snap.wallet_balance:.4f}|eq:{snap.equity:.4f}"
        identity_fp = runtime_demo_account_fingerprint(
            api_domain=self.api_domain,
            account_created_at=self.account_created_at,
            wallet_snapshot_reference=wallet_ref if self.current_epoch is None else (
                self.current_epoch.wallet_snapshot_reference or wallet_ref
            ),
        )
        current = self.current_epoch
        if current is None:
            ep = self._start_epoch(snap, fp, trade_count, reflection_count, wallet_ref, identity_fp)
            if persist:
                self.persist()
            return ep

        if self._is_fund_reset(current, snap):
            current.superseded = True
            current.retained_trade_count = trade_count
            current.retained_reflection_count = reflection_count
            ep = self._start_epoch(snap, fp, 0, 0, wallet_ref, identity_fp)
            if persist:
                self.persist()
            return ep

        current.fingerprint = fp
        current.wallet_balance = snap.wallet_balance
        current.runtime_demo_account_fingerprint = current.runtime_demo_account_fingerprint or identity_fp
        current.api_domain = self.api_domain
        if persist:
            self.persist()
        return current

    def _start_epoch(
        self,
        snap: DemoAccountSnapshot,
        fingerprint: str,
        trade_count: int,
        reflection_count: int,
        wallet_ref: str,
        identity_fp: str,
    ) -> AccountEpoch:
        self._epoch_seq += 1
        ep = AccountEpoch(
            epoch_id=f"epoch-{self._epoch_seq:04d}",
            started_at=time.time(),
            fingerprint=fingerprint,
            wallet_balance=snap.wallet_balance,
            retained_trade_count=trade_count,
            retained_reflection_count=reflection_count,
            api_domain=self.api_domain,
            account_created_at=self.account_created_at,
            wallet_snapshot_reference=wallet_ref,
            runtime_demo_account_fingerprint=identity_fp,
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
            "account_epoch": cur.epoch_id if cur else None,
            "account_fingerprint": cur.fingerprint if cur else None,
            "runtime_demo_account_fingerprint": cur.runtime_demo_account_fingerprint if cur else None,
            "api_domain": (cur.api_domain if cur else self.api_domain),
            "account_created_at": (cur.account_created_at if cur else self.account_created_at),
            "wallet_snapshot_reference": cur.wallet_snapshot_reference if cur else None,
            "account_epoch_present": bool(cur and cur.epoch_id),
            "account_fingerprint_present": bool(cur and (cur.fingerprint or cur.runtime_demo_account_fingerprint)),
            "epochs": [e.to_dict() for e in self.epochs],
        }
