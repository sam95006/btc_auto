"""Expiring one-time email verification + password-reset tokens."""
from __future__ import annotations

import hashlib
import hmac
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.nexus_public_auth.passwords import new_token
from backend.nexus_public_auth.store import _new_id, _utcnow


VERIFY_TTL_SEC = 24 * 3600
RESET_TTL_SEC = 3600


@dataclass
class AuthTokenRecord:
    token_id: str
    account_id: str
    purpose: str  # email_verify | password_reset
    token_hash: str
    expires_at_epoch: float
    consumed: bool = False
    consumed_at: Optional[str] = None
    created_at: str = field(default_factory=_utcnow)


def _hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


class AuthTokenStore:
    """In-memory token vault — stores only hashes, never plaintext tokens."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, AuthTokenRecord] = {}

    def issue(
        self,
        *,
        account_id: str,
        purpose: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        raw = new_token(32)
        now = time.time()
        rec = AuthTokenRecord(
            token_id=_new_id("tok"),
            account_id=account_id,
            purpose=purpose,
            token_hash=_hash_token(raw),
            expires_at_epoch=now + float(ttl_seconds),
        )
        with self._lock:
            # Invalidate prior unused tokens of same purpose for account.
            for tid, existing in list(self._by_id.items()):
                if (
                    existing.account_id == account_id
                    and existing.purpose == purpose
                    and not existing.consumed
                ):
                    existing.consumed = True
                    existing.consumed_at = _utcnow()
                    self._by_id[tid] = existing
            self._by_id[rec.token_id] = rec
        return {
            "token_id": rec.token_id,
            "token": raw,
            "purpose": purpose,
            "expires_at_epoch": rec.expires_at_epoch,
            "ttl_seconds": ttl_seconds,
        }

    def consume(self, raw_token: str, *, purpose: str) -> AuthTokenRecord:
        digest = _hash_token(raw_token)
        now = time.time()
        with self._lock:
            match: Optional[AuthTokenRecord] = None
            for rec in self._by_id.values():
                if hmac.compare_digest(rec.token_hash, digest) and rec.purpose == purpose:
                    match = rec
                    break
            if match is None:
                raise ValueError("invalid_or_unknown_token")
            if match.consumed:
                raise ValueError("token_already_used")
            if now > match.expires_at_epoch:
                raise ValueError("token_expired")
            match.consumed = True
            match.consumed_at = _utcnow()
            self._by_id[match.token_id] = match
            return match

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "token_count": len(self._by_id),
                "consumed": sum(1 for t in self._by_id.values() if t.consumed),
            }


_DEFAULT_TOKENS: Optional[AuthTokenStore] = None
_LOCK = threading.Lock()


def get_default_token_store() -> AuthTokenStore:
    global _DEFAULT_TOKENS
    with _LOCK:
        if _DEFAULT_TOKENS is None:
            _DEFAULT_TOKENS = AuthTokenStore()
        return _DEFAULT_TOKENS


def reset_default_token_store() -> AuthTokenStore:
    global _DEFAULT_TOKENS
    with _LOCK:
        _DEFAULT_TOKENS = AuthTokenStore()
        return _DEFAULT_TOKENS
