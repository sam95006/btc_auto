"""Restart recovery / single-owner leader lock for bounded Demo sessions."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SessionRecoverySnapshot:
    session_id: str
    policy_version: str
    state: str
    deadline_ts: float
    entries_total: int
    completed_trades: int
    consecutive_losses: int
    bad_process_outcomes: int
    session_net_pnl: float
    write_window_open: bool
    leader_token: str
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionRecoverySnapshot":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})  # type: ignore[arg-type]


class LeaderLockError(RuntimeError):
    pass


class SessionRecoveryStore:
    """Filesystem leader lock + durable counters (no secret material)."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.root / "leader_lock.json"
        self.snap_path = self.root / "session_recovery.json"

    def acquire(self, leader_token: str, *, session_id: str) -> None:
        now = time.time()
        if self.lock_path.exists():
            lock = json.loads(self.lock_path.read_text(encoding="utf-8"))
            if lock.get("leader_token") and lock.get("leader_token") != leader_token:
                if lock.get("session_id") == session_id:
                    raise LeaderLockError("SECOND_CONTROLLER_REFUSED")
                # Different session: refuse if lock fresh (< 120s) unless released.
                if now - float(lock.get("updated_at") or 0) < 120:
                    raise LeaderLockError("LEADER_LOCK_HELD")
        self.lock_path.write_text(
            json.dumps(
                {
                    "leader_token": leader_token,
                    "session_id": session_id,
                    "updated_at": now,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def heartbeat(self, leader_token: str) -> None:
        if not self.lock_path.exists():
            raise LeaderLockError("LEADER_LOCK_MISSING")
        lock = json.loads(self.lock_path.read_text(encoding="utf-8"))
        if lock.get("leader_token") != leader_token:
            raise LeaderLockError("LEADER_TOKEN_MISMATCH")
        lock["updated_at"] = time.time()
        self.lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    def release(self, leader_token: str) -> None:
        if not self.lock_path.exists():
            return
        lock = json.loads(self.lock_path.read_text(encoding="utf-8"))
        if lock.get("leader_token") != leader_token:
            raise LeaderLockError("LEADER_TOKEN_MISMATCH")
        self.lock_path.unlink(missing_ok=True)

    def save(self, snap: SessionRecoverySnapshot) -> None:
        self.snap_path.write_text(json.dumps(snap.to_dict(), indent=2) + "\n", encoding="utf-8")

    def load(self) -> SessionRecoverySnapshot | None:
        if not self.snap_path.exists():
            return None
        return SessionRecoverySnapshot.from_dict(json.loads(self.snap_path.read_text(encoding="utf-8")))

    def recover_or_block(self, *, leader_token: str, expected_session_id: str) -> dict[str, Any]:
        snap = self.load()
        if snap is None:
            return {
                "ok": False,
                "reason": "SESSION_RECOVERY_BLOCKED",
                "new_entry_blocked": True,
                "detail": "missing_recovery_snapshot",
            }
        if snap.session_id != expected_session_id:
            return {
                "ok": False,
                "reason": "SESSION_RECOVERY_BLOCKED",
                "new_entry_blocked": True,
                "detail": "session_id_mismatch",
            }
        try:
            self.acquire(leader_token, session_id=expected_session_id)
        except LeaderLockError as exc:
            return {
                "ok": False,
                "reason": "SESSION_RECOVERY_BLOCKED",
                "new_entry_blocked": True,
                "detail": str(exc),
            }
        # Counters / deadline must not reset.
        return {
            "ok": True,
            "reason": "RECOVERED",
            "new_entry_blocked": False,
            "snapshot": snap.to_dict(),
            "preserved": {
                "entries_total": snap.entries_total,
                "consecutive_losses": snap.consecutive_losses,
                "bad_process_outcomes": snap.bad_process_outcomes,
                "deadline_ts": snap.deadline_ts,
                "session_net_pnl": snap.session_net_pnl,
            },
        }
