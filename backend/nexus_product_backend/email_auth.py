"""Member email lifecycle: verification and password reset.

Builds on the existing NEXUS member foundation (accounts / email_identities /
password_credentials / auth_sessions / one_time_tokens). It introduces NO
parallel auth or token system and NO new database table — it reuses the
existing ``ProductRepository.issue_one_time_token`` /
``consume_one_time_token`` primitives backed by ``nexus.one_time_tokens``.

Security properties (enforced by the reused store):
  * Tokens are cryptographically random (``secrets.token_urlsafe``), high
    entropy, purpose-bound and account-bound.
  * Only the SHA-256 hash of a token is persisted; the raw token is returned
    once for delivery and is never stored or logged here.
  * Tokens are one-time (consumed atomically), expiring; replay / expiry /
    wrong-purpose / already-used are all denied by the store.
  * Verification and reset tokens use different purposes and are not
    interchangeable.
  * ``forgot_password`` always returns a generic response to resist account
    enumeration.
  * A successful password reset revokes ALL existing sessions for the account.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from backend.nexus_product_backend.email_provider import EmailProvider, NullEmailProvider

PURPOSE_EMAIL_VERIFY = "email_verify"
PURPOSE_PASSWORD_RESET = "password_reset"

VERIFY_TTL_MINUTES = 24 * 60
RESET_TTL_MINUTES = 60
RESEND_COOLDOWN_SECONDS = 60
MIN_PASSWORD_LENGTH = 12

GENERIC_FORGOT_MESSAGE = "If an account exists for that email, a reset link has been sent."
GENERIC_RESEND_MESSAGE = "If an account exists and is not yet verified, a verification link has been sent."


class EmailTokenRepo(Protocol):
    def get_account_by_email(self, email: str) -> Optional[dict[str, Any]]: ...

    def issue_one_time_token(self, account_id: str, purpose: str, *, ttl_minutes: int) -> str: ...

    def consume_one_time_token(self, raw: str, purpose: str) -> Optional[str]: ...

    def supersede_unconsumed_tokens(self, account_id: str, purpose: str) -> int: ...

    def mark_email_verified_and_activate(self, account_id: str) -> bool: ...

    def update_password_hash(self, account_id: str, password_hash: str) -> None: ...

    def revoke_all_sessions(self, account_id: str) -> int: ...

    def seconds_since_last_token(self, account_id: str, purpose: str) -> Optional[float]: ...


@dataclass
class EmailActionResult:
    ok: bool
    code: str
    status_code: int
    message: str = ""
    delivery: Optional[dict[str, Any]] = None
    revoked_sessions: int = 0


class MemberEmailService:
    def __init__(
        self,
        repo: EmailTokenRepo,
        *,
        hash_password: Optional[Callable[[str], str]],
        provider: Optional[EmailProvider] = None,
        frontend_base_url: str = "",
        resend_cooldown_seconds: int = RESEND_COOLDOWN_SECONDS,
    ) -> None:
        self._repo = repo
        self._hash_password = hash_password
        self._provider = provider or NullEmailProvider()
        self._frontend_base = (frontend_base_url or "").rstrip("/")
        self._cooldown = int(resend_cooldown_seconds)

    # ----- link construction (raw token only ever placed in the emailed link) -----
    def _verify_link(self, raw_token: str) -> str:
        return f"{self._frontend_base}/verify-email?token={raw_token}"

    def _reset_link(self, raw_token: str) -> str:
        return f"{self._frontend_base}/reset-password?token={raw_token}"

    # ----- issuance (also used at registration time in enforced mode) -----
    def issue_verification(self, *, account_id: str, email: str) -> EmailActionResult:
        # Supersede prior unconsumed verification tokens per explicit policy.
        self._repo.supersede_unconsumed_tokens(account_id, PURPOSE_EMAIL_VERIFY)
        raw = self._repo.issue_one_time_token(
            account_id, PURPOSE_EMAIL_VERIFY, ttl_minutes=VERIFY_TTL_MINUTES
        )
        delivery = self._provider.send_verification_email(
            to_email=email, verify_link=self._verify_link(raw)
        )
        return EmailActionResult(
            ok=True,
            code="verification_issued",
            status_code=200,
            message="verification_issued",
            delivery=delivery.to_audit_dict(),
        )

    def verify_email(self, *, raw_token: str) -> EmailActionResult:
        if not raw_token:
            return EmailActionResult(False, "invalid_token", 400, "invalid_or_expired_token")
        account_id = self._repo.consume_one_time_token(raw_token, PURPOSE_EMAIL_VERIFY)
        if not account_id:
            # Unknown, expired, already-used, or wrong-purpose token.
            return EmailActionResult(False, "invalid_token", 400, "invalid_or_expired_token")
        activated = self._repo.mark_email_verified_and_activate(account_id)
        if not activated:
            # The account is not in PENDING_VERIFICATION (e.g. DISABLED, or a
            # stale token for an already-active account). Never reactivate; fail
            # closed with a generic, non-enumerating response.
            return EmailActionResult(False, "invalid_token", 400, "invalid_or_expired_token")
        return EmailActionResult(True, "verified", 200, "email_verified")

    def resend_verification(self, *, email: str) -> EmailActionResult:
        account = self._repo.get_account_by_email(email)
        generic = EmailActionResult(True, "resend_generic", 200, GENERIC_RESEND_MESSAGE)
        if not account:
            return generic
        status = str(account.get("status", "")).lower()
        if status == "active":
            return generic  # already verified; do not reveal
        account_id = account["account_id"]
        elapsed = self._repo.seconds_since_last_token(account_id, PURPOSE_EMAIL_VERIFY)
        if elapsed is not None and elapsed < self._cooldown:
            return EmailActionResult(True, "resend_cooldown", 200, GENERIC_RESEND_MESSAGE)
        return self.issue_verification(account_id=account_id, email=email)

    def forgot_password(self, *, email: str) -> EmailActionResult:
        account = self._repo.get_account_by_email(email)
        generic = EmailActionResult(True, "forgot_generic", 200, GENERIC_FORGOT_MESSAGE)
        if not account:
            return generic
        account_id = account["account_id"]
        self._repo.supersede_unconsumed_tokens(account_id, PURPOSE_PASSWORD_RESET)
        raw = self._repo.issue_one_time_token(
            account_id, PURPOSE_PASSWORD_RESET, ttl_minutes=RESET_TTL_MINUTES
        )
        self._provider.send_password_reset_email(to_email=email, reset_link=self._reset_link(raw))
        return generic

    def reset_password(self, *, raw_token: str, new_password: str) -> EmailActionResult:
        if not raw_token:
            return EmailActionResult(False, "invalid_token", 400, "invalid_or_expired_token")
        if not new_password or len(new_password) < MIN_PASSWORD_LENGTH:
            return EmailActionResult(False, "weak_password", 400, "weak_password")
        # Fail closed if the canonical Argon2 hasher is unavailable, BEFORE the
        # reset token is consumed, so the token remains usable and the password
        # is never downgraded to a weaker hash.
        if self._hash_password is None:
            return EmailActionResult(False, "service_unavailable", 503, "service_unavailable")
        account_id = self._repo.consume_one_time_token(raw_token, PURPOSE_PASSWORD_RESET)
        if not account_id:
            return EmailActionResult(False, "invalid_token", 400, "invalid_or_expired_token")
        self._repo.update_password_hash(account_id, self._hash_password(new_password))
        revoked = self._repo.revoke_all_sessions(account_id)
        return EmailActionResult(
            True, "password_reset", 200, "password_reset", revoked_sessions=int(revoked)
        )
