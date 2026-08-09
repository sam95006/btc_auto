"""In-memory closed-beta invite + member access store (LOCAL_OR_STAGING_ONLY)."""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.nexus_closed_beta.constants import (
    BETA_ACCESS_STATUSES,
    DEFAULT_INVITE_TTL_SECONDS,
    INVITE_STATUSES,
)


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _hash_code(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


@dataclass
class BetaInvite:
    invite_id: str
    code_hash: str
    code_hint: str
    email_hint: Optional[str] = None
    status: str = "PENDING"
    created_at: str = field(default_factory=_utcnow)
    expires_at_epoch: float = 0.0
    redeemed_at: Optional[str] = None
    redeemed_by_account_id: Optional[str] = None
    revoked_at: Optional[str] = None
    revoked_by: Optional[str] = None
    created_by: str = "founder_admin"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemberBetaAccess:
    account_id: str
    status: str = "INVITED"
    invite_id: Optional[str] = None
    activated_at: Optional[str] = None
    revoked_at: Optional[str] = None
    expired_at: Optional[str] = None
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class BetaAuditEvent:
    event_id: str
    action: str
    result: str
    actor: str
    invite_id: Optional[str] = None
    account_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)


class ClosedBetaStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.invites: dict[str, BetaInvite] = {}
        self.invites_by_hash: dict[str, str] = {}
        self.access: dict[str, MemberBetaAccess] = {}
        self.audit: list[BetaAuditEvent] = []

    def append_audit(
        self,
        action: str,
        result: str,
        *,
        actor: str,
        invite_id: Optional[str] = None,
        account_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> BetaAuditEvent:
        ev = BetaAuditEvent(
            event_id=_new_id("betaaud"),
            action=action,
            result=result,
            actor=actor,
            invite_id=invite_id,
            account_id=account_id,
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self.audit.append(ev)
            if len(self.audit) > 2000:
                self.audit = self.audit[-2000:]
        return ev

    def create_invite(
        self,
        *,
        email_hint: Optional[str] = None,
        ttl_seconds: int = DEFAULT_INVITE_TTL_SECONDS,
        created_by: str = "founder_admin",
        raw_code: Optional[str] = None,
    ) -> tuple[BetaInvite, str]:
        code = (raw_code or secrets.token_urlsafe(18)).strip()
        code_hash = _hash_code(code)
        with self._lock:
            if code_hash in self.invites_by_hash:
                raise ValueError("invite_code_collision")
            invite = BetaInvite(
                invite_id=_new_id("inv"),
                code_hash=code_hash,
                code_hint=code[:4] + "…" + code[-3:] if len(code) > 8 else code[:2] + "…",
                email_hint=(email_hint or "").strip().lower() or None,
                status="PENDING",
                expires_at_epoch=time.time() + max(60, int(ttl_seconds)),
                created_by=created_by,
            )
            if invite.status not in INVITE_STATUSES:
                raise ValueError("invalid_invite_status")
            self.invites[invite.invite_id] = invite
            self.invites_by_hash[code_hash] = invite.invite_id
        self.append_audit(
            "invite.create",
            "ALLOW",
            actor=created_by,
            invite_id=invite.invite_id,
            metadata={"email_hint": invite.email_hint, "expires_at_epoch": invite.expires_at_epoch},
        )
        return invite, code

    def get_invite(self, invite_id: str) -> Optional[BetaInvite]:
        with self._lock:
            return self.invites.get(invite_id)

    def find_by_code(self, raw_code: str) -> Optional[BetaInvite]:
        code_hash = _hash_code(raw_code or "")
        with self._lock:
            invite_id = self.invites_by_hash.get(code_hash)
            if not invite_id:
                return None
            return self.invites.get(invite_id)

    def put_invite(self, invite: BetaInvite) -> None:
        with self._lock:
            self.invites[invite.invite_id] = invite

    def get_access(self, account_id: str) -> Optional[MemberBetaAccess]:
        with self._lock:
            return self.access.get(account_id)

    def put_access(self, access: MemberBetaAccess) -> None:
        if access.status not in BETA_ACCESS_STATUSES:
            raise ValueError(f"invalid_beta_access_status:{access.status}")
        access.updated_at = _utcnow()
        with self._lock:
            self.access[access.account_id] = access

    def list_audit(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self.audit)[-max(1, min(200, limit)) :]
        return [
            {
                "event_id": e.event_id,
                "action": e.action,
                "result": e.result,
                "actor": e.actor,
                "invite_id": e.invite_id,
                "account_id": e.account_id,
                "metadata": e.metadata,
                "created_at": e.created_at,
            }
            for e in rows
        ]


_STORE: Optional[ClosedBetaStore] = None
_LOCK = threading.Lock()


def get_closed_beta_store() -> ClosedBetaStore:
    global _STORE
    with _LOCK:
        if _STORE is None:
            _STORE = ClosedBetaStore()
        return _STORE
