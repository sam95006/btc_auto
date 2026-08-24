"""Durable bounded-session lease ownership — survives process restart."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ActiveLeaseRecord:
    session_id: str
    authorized_at: str
    expires_at: str
    expected_runtime_sha: str
    founder_auth_consumed: bool
    leader_token: str
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "authorized_at": self.authorized_at,
            "expires_at": self.expires_at,
            "expected_runtime_sha": self.expected_runtime_sha,
            "founder_auth_consumed": self.founder_auth_consumed,
            "leader_token": self.leader_token,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActiveLeaseRecord:
        return cls(
            session_id=str(data["session_id"]),
            authorized_at=str(data["authorized_at"]),
            expires_at=str(data["expires_at"]),
            expected_runtime_sha=str(data.get("expected_runtime_sha") or ""),
            founder_auth_consumed=bool(data.get("founder_auth_consumed")),
            leader_token=str(data.get("leader_token") or ""),
            updated_at=float(data.get("updated_at") or 0.0),
        )


def _parse_expires(expires_at: str) -> datetime:
    return datetime.fromisoformat(expires_at.replace("Z", "+00:00"))


class DurableLeaseStore:
    """Filesystem-backed active lease — complements SessionRecoveryStore leader lock."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lease_path = self.root / "active_bounded_lease.json"

    def load(self) -> ActiveLeaseRecord | None:
        if not self.lease_path.is_file():
            return None
        payload = json.loads(self.lease_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return ActiveLeaseRecord.from_dict(payload)

    def save(self, record: ActiveLeaseRecord) -> None:
        self.lease_path.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def clear(self) -> None:
        if self.lease_path.is_file():
            self.lease_path.unlink()

    def is_expired(self, record: ActiveLeaseRecord | None = None) -> bool:
        row = record or self.load()
        if row is None:
            return True
        return _parse_expires(row.expires_at) <= datetime.now(timezone.utc)

    def claim_or_resume(
        self,
        *,
        session_id: str,
        authorized_at: str,
        expires_at: str,
        expected_runtime_sha: str,
        leader_token: str,
        founder_auth_consumed: bool,
    ) -> dict[str, Any]:
        existing = self.load()
        now = time.time()
        if existing is not None and not self.is_expired(existing):
            if existing.session_id != session_id:
                return {"ok": False, "reason": "duplicate_active_lease", "owner_session_id": existing.session_id}
            if existing.leader_token and existing.leader_token != leader_token:
                return {"ok": False, "reason": "execution_owner_mismatch", "owner_session_id": existing.session_id}
        record = ActiveLeaseRecord(
            session_id=session_id,
            authorized_at=authorized_at,
            expires_at=expires_at,
            expected_runtime_sha=expected_runtime_sha,
            founder_auth_consumed=founder_auth_consumed,
            leader_token=leader_token,
            updated_at=now,
        )
        self.save(record)
        return {"ok": True, "record": record.to_dict(), "resumed": existing is not None and existing.session_id == session_id}
