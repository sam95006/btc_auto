"""In-memory non-production store for public identity & membership."""
from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from backend.nexus_public_auth.constants import BILLING_PROVIDER, DEPLOYMENT_MODE, LIVE_BILLING_ENABLED
from backend.nexus_public_auth.hard_bans import (
    HardBanViolation,
    refuse_live_billing,
    refuse_production_customer_database,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


@dataclass
class PublicAccount:
    account_id: str
    email: str
    display_name: str
    tier: str = "Free"
    member_roles: list[str] = field(default_factory=lambda: ["member"])
    org_roles: dict[str, list[str]] = field(default_factory=dict)  # org_id -> roles
    team_roles: dict[str, list[str]] = field(default_factory=dict)  # team_id -> roles
    status: str = "active"  # active | deletion_pending | deleted
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    deletion_requested_at: Optional[str] = None
    consent: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class PublicSession:
    session_id: str
    account_id: str
    token_jti: str
    issued_at: str
    expires_at: str
    revoked: bool = False
    revoked_at: Optional[str] = None
    revoke_reason: Optional[str] = None
    realm: str = ""
    issuer: str = ""


@dataclass
class AuditEvent:
    event_id: str
    account_id: Optional[str]
    action: str
    result: str
    metadata: dict[str, Any]
    created_at: str = field(default_factory=_utcnow)


class PublicAuthStore:
    """LOCAL_OR_STAGING_ONLY identity store. Never a production-customer DB."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.deployment_mode = DEPLOYMENT_MODE
        self.billing_provider = BILLING_PROVIDER
        self.live_billing_enabled = LIVE_BILLING_ENABLED
        self.accounts: dict[str, PublicAccount] = {}
        self.sessions: dict[str, PublicSession] = {}
        self.sessions_by_jti: dict[str, str] = {}
        self.audit: list[AuditEvent] = []
        self.exports: dict[str, dict[str, Any]] = {}
        self._assert_non_production()

    def _assert_non_production(self) -> None:
        if self.live_billing_enabled:
            refuse_live_billing()
        if self.deployment_mode != "LOCAL_OR_STAGING_ONLY":
            refuse_production_customer_database()
        if self.billing_provider != "NONE_NON_PRODUCTION":
            refuse_live_billing()

    def create_account(
        self,
        email: str,
        display_name: str,
        *,
        tier: str = "Free",
    ) -> PublicAccount:
        self._assert_non_production()
        account = PublicAccount(
            account_id=_new_id("acct"),
            email=email.strip().lower(),
            display_name=display_name.strip(),
            tier=tier,
        )
        with self._lock:
            self.accounts[account.account_id] = account
        return deepcopy(account)

    def get_account(self, account_id: str) -> Optional[PublicAccount]:
        with self._lock:
            acct = self.accounts.get(account_id)
            return deepcopy(acct) if acct else None

    def update_account(self, account: PublicAccount) -> PublicAccount:
        account.updated_at = _utcnow()
        with self._lock:
            self.accounts[account.account_id] = account
        return deepcopy(account)

    def put_session(self, session: PublicSession) -> PublicSession:
        with self._lock:
            self.sessions[session.session_id] = session
            self.sessions_by_jti[session.token_jti] = session.session_id
        return deepcopy(session)

    def get_session(self, session_id: str) -> Optional[PublicSession]:
        with self._lock:
            s = self.sessions.get(session_id)
            return deepcopy(s) if s else None

    def get_session_by_jti(self, jti: str) -> Optional[PublicSession]:
        with self._lock:
            sid = self.sessions_by_jti.get(jti)
            if not sid:
                return None
            s = self.sessions.get(sid)
            return deepcopy(s) if s else None

    def append_audit(
        self,
        action: str,
        result: str,
        *,
        account_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=_new_id("aud"),
            account_id=account_id,
            action=action,
            result=result,
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self.audit.append(event)
        return deepcopy(event)

    def list_audit(self, account_id: Optional[str] = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.audit
            if account_id is not None:
                rows = [e for e in rows if e.account_id == account_id]
            return [asdict(e) for e in rows]

    def save_export(self, export_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self.exports[export_id] = payload

    def get_export(self, export_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            payload = self.exports.get(export_id)
            return deepcopy(payload) if payload else None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "deployment_mode": self.deployment_mode,
                "billing_provider": self.billing_provider,
                "live_billing_enabled": self.live_billing_enabled,
                "account_count": len(self.accounts),
                "session_count": len(self.sessions),
                "audit_count": len(self.audit),
            }


# Module-level default store for local/staging foundations.
_DEFAULT_STORE: Optional[PublicAuthStore] = None
_DEFAULT_LOCK = threading.Lock()


def get_default_store() -> PublicAuthStore:
    global _DEFAULT_STORE
    with _DEFAULT_LOCK:
        if _DEFAULT_STORE is None:
            _DEFAULT_STORE = PublicAuthStore()
        return _DEFAULT_STORE


def reset_default_store() -> PublicAuthStore:
    global _DEFAULT_STORE
    with _DEFAULT_LOCK:
        _DEFAULT_STORE = PublicAuthStore()
        return _DEFAULT_STORE


def enable_live_billing_forbidden() -> None:
    """Adversarial helper — attempting to flip live billing must raise."""
    raise HardBanViolation("HARD BAN: cannot enable live billing on PublicAuthStore")
