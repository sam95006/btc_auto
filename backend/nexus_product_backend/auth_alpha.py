"""Auth alpha service — Argon2 passwords, sessions, tokens, MFA hooks."""
from __future__ import annotations

from typing import Any, Callable

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from backend.nexus_product_backend.repository import ProductRepository

RateLimitHook = Callable[[str, str], None]


class AuthAlphaService:
    ALPHA_READY = "AUTH_ALPHA_READY"

    def __init__(
        self,
        repo: ProductRepository,
        *,
        rate_limit_hook: RateLimitHook | None = None,
    ):
        self.repo = repo
        self._hasher = PasswordHasher()
        self._rate_limit_hook = rate_limit_hook

    def register(self, email: str, password: str) -> dict[str, Any]:
        existing = self.repo.get_account_by_email(email)
        if existing:
            raise ValueError("email_already_registered")
        password_hash = self._hasher.hash(password)
        account_id = self.repo.create_account(email, password_hash)
        session_id = self.repo.create_session(account_id)
        return {"account_id": account_id, "session_id": session_id, "status": self.ALPHA_READY}

    def register_staging_member(
        self, *, email: str, password: str, display_name: str, founder: bool
    ) -> dict[str, Any]:
        if len(password) < 12:
            raise ValueError("weak_password")
        password_hash = self._hasher.hash(password)
        account_id, session_id = self.repo.register_staging_account(
            email=email, password_hash=password_hash, display_name=display_name, founder=founder
        )
        return {"account_id": account_id, "session_id": session_id}

    def login(self, email: str, password: str, *, ip: str = "unknown") -> dict[str, Any]:
        if self._rate_limit_hook:
            self._rate_limit_hook(email, ip)
        account = self.repo.get_account_by_email(email)
        if not account or not account.get("password_hash"):
            raise ValueError("invalid_credentials")
        try:
            self._hasher.verify(account["password_hash"], password)
        except VerifyMismatchError as exc:
            raise ValueError("invalid_credentials") from exc
        session_id = self.repo.create_session(account["account_id"])
        return {
            "account_id": account["account_id"],
            "session_id": session_id,
            "email": account["email"],
        }

    def logout(self, session_id: str) -> None:
        self.repo.revoke_session(session_id)

    def resolve_session(self, session_id: str) -> dict[str, Any] | None:
        return self.repo.get_active_session(session_id)

    def issue_password_reset(self, email: str) -> str | None:
        account = self.repo.get_account_by_email(email)
        if not account:
            return None
        return self.repo.issue_one_time_token(account["account_id"], "password_reset")

    def reset_password(self, token: str, new_password: str) -> None:
        account_id = self.repo.consume_one_time_token(token, "password_reset")
        if not account_id:
            raise ValueError("invalid_or_expired_token")
        password_hash = self._hasher.hash(new_password)
        self.repo.pool.execute(
            """
            UPDATE nexus.password_credentials
            SET password_hash = %s, updated_at = NOW()
            WHERE account_id = %s
            """,
            (password_hash, account_id),
        )
