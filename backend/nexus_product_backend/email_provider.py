"""Transactional email provider abstraction for NEXUS member lifecycle.

This module defines the provider seam used to deliver member verification and
password-reset emails. It deliberately contains NO Chinese AI/provider products
and NO AI involvement — delivery is deterministic transactional email only.

Security invariants:
  * Raw verification/reset tokens and full links are NEVER logged. Only a
    coarse, non-reversible delivery-audit record is retained (provider name,
    purpose, a masked recipient, status, attempt count, and error class).
  * Provider secrets and full provider responses are never logged or returned.
  * When no provider is configured the factory returns a NullEmailProvider that
    reports ``configured == False`` and fails delivery closed (it does not
    pretend to have sent anything).

The concrete network provider is intentionally not wired to any specific
vendor here: a real provider must be supplied externally (env configuration).
Until then the system runs with the NullEmailProvider and the caller treats
delivery as unavailable rather than fabricating success.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

RESEND_API_URL = "https://api.resend.com/emails"


def mask_email(email: str) -> str:
    """Return a non-reversible-ish masked recipient safe for audit logs."""
    email = (email or "").strip()
    if "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    head = local[:1] if local else ""
    return f"{head}***@{domain}"


@dataclass
class DeliveryAttempt:
    """Non-sensitive audit record of a single delivery attempt series."""

    provider: str
    purpose: str
    recipient_masked: str
    delivered: bool
    status: str
    attempts: int
    error_class: Optional[str] = None
    created_at_epoch: float = field(default_factory=time.time)

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "purpose": self.purpose,
            "recipient_masked": self.recipient_masked,
            "delivered": self.delivered,
            "status": self.status,
            "attempts": self.attempts,
            "error_class": self.error_class,
        }


class EmailProvider(Protocol):
    name: str
    configured: bool

    def send_verification_email(self, *, to_email: str, verify_link: str) -> DeliveryAttempt: ...

    def send_password_reset_email(self, *, to_email: str, reset_link: str) -> DeliveryAttempt: ...

    def health(self) -> dict[str, Any]: ...


class NullEmailProvider:
    """Default provider used when no transactional email vendor is configured.

    It never fabricates a successful send. Callers must treat delivery as
    unavailable and surface an explicit "provider not configured" state.
    """

    name = "null"
    configured = False

    def _attempt(self, purpose: str, to_email: str) -> DeliveryAttempt:
        return DeliveryAttempt(
            provider=self.name,
            purpose=purpose,
            recipient_masked=mask_email(to_email),
            delivered=False,
            status="PROVIDER_NOT_CONFIGURED",
            attempts=0,
            error_class=None,
        )

    def send_verification_email(self, *, to_email: str, verify_link: str) -> DeliveryAttempt:
        del verify_link  # never logged
        return self._attempt("email_verify", to_email)

    def send_password_reset_email(self, *, to_email: str, reset_link: str) -> DeliveryAttempt:
        del reset_link  # never logged
        return self._attempt("password_reset", to_email)

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "configured": False, "status": "NOT_CONFIGURED"}


class CallableEmailProvider:
    """Adapter that wraps a real transactional send callable with bounded retry
    and a timeout budget, producing only non-sensitive audit records.

    ``sender`` is ``sender(purpose, to_email, link) -> None`` and must raise on
    failure. It is supplied by whoever wires a concrete vendor; this class does
    not embed any vendor SDK or credentials.
    """

    def __init__(
        self,
        *,
        name: str,
        sender: Callable[[str, str, str], None],
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.name = name
        self.configured = True
        self._sender = sender
        self._max_attempts = max(1, int(max_attempts))
        self._backoff = max(0.0, float(retry_backoff_seconds))
        self._sleep = sleep

    def _send(self, purpose: str, to_email: str, link: str) -> DeliveryAttempt:
        last_error: Optional[str] = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                self._sender(purpose, to_email, link)
                return DeliveryAttempt(
                    provider=self.name,
                    purpose=purpose,
                    recipient_masked=mask_email(to_email),
                    delivered=True,
                    status="SENT",
                    attempts=attempt,
                )
            except Exception as exc:  # noqa: BLE001 - class name only, never the message
                last_error = type(exc).__name__
                if attempt < self._max_attempts and self._backoff:
                    self._sleep(self._backoff)
        return DeliveryAttempt(
            provider=self.name,
            purpose=purpose,
            recipient_masked=mask_email(to_email),
            delivered=False,
            status="DELIVERY_FAILED",
            attempts=self._max_attempts,
            error_class=last_error,
        )

    def send_verification_email(self, *, to_email: str, verify_link: str) -> DeliveryAttempt:
        return self._send("email_verify", to_email, verify_link)

    def send_password_reset_email(self, *, to_email: str, reset_link: str) -> DeliveryAttempt:
        return self._send("password_reset", to_email, reset_link)

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "configured": True, "status": "READY"}


def _default_resend_transport(*, api_key: str, payload: dict[str, Any], timeout: float) -> int:
    """POST an email to the Resend API and return the HTTP status code.

    Raises on transport/timeout errors (the caller classifies and may retry).
    The API key travels only in the Authorization header and is never returned
    or logged.
    """
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        RESEND_API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


class ResendEmailProvider:
    """Concrete transactional provider backed by the Resend Email API.

    Retries only transient failures (429 / 5xx / transport timeout) up to a
    bounded number of attempts; authentication (401/403) and other 4xx are
    permanent and fail closed without retry. The API key, raw tokens, full
    links, and message bodies are never logged or placed in audit records.
    """

    name = "resend"

    def __init__(
        self,
        *,
        api_key: str,
        from_address: str,
        transport: Optional[Callable[..., int]] = None,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._from = from_address
        self._transport = transport or _default_resend_transport
        self._timeout = float(timeout_seconds)
        self._max_attempts = max(1, int(max_attempts))
        self._backoff = max(0.0, float(retry_backoff_seconds))
        self._sleep = sleep
        self.configured = bool(api_key) and bool(from_address)
        self._degraded = False

    # -- message composition (link is delivered in the body, never logged) --
    @staticmethod
    def _verification_body(link: str) -> tuple[str, str, str]:
        subject = "Verify your NEXUS account"
        text = (
            "Welcome to NEXUS. Please verify your email address by opening the "
            f"link below:\n\n{link}\n\nThis link expires in 24 hours. If you did "
            "not create a NEXUS account you can ignore this message."
        )
        html = (
            "<p>Welcome to NEXUS. Please verify your email address:</p>"
            f'<p><a href="{link}">Verify my email</a></p>'
            "<p>This link expires in 24 hours. If you did not create a NEXUS "
            "account you can ignore this message.</p>"
        )
        return subject, text, html

    @staticmethod
    def _reset_body(link: str) -> tuple[str, str, str]:
        subject = "Reset your NEXUS password"
        text = (
            "A password reset was requested for your NEXUS account. Open the link "
            f"below to choose a new password:\n\n{link}\n\nThis link expires in 1 "
            "hour. If you did not request this you can ignore this message."
        )
        html = (
            "<p>A password reset was requested for your NEXUS account.</p>"
            f'<p><a href="{link}">Reset my password</a></p>'
            "<p>This link expires in 1 hour. If you did not request this you can "
            "ignore this message.</p>"
        )
        return subject, text, html

    def _send(self, purpose: str, to_email: str, subject: str, text: str, html: str) -> DeliveryAttempt:
        if not self.configured:
            return DeliveryAttempt(
                provider=self.name,
                purpose=purpose,
                recipient_masked=mask_email(to_email),
                delivered=False,
                status="NOT_CONFIGURED",
                attempts=0,
            )
        payload = {"from": self._from, "to": [to_email], "subject": subject, "text": text, "html": html}
        last_error: Optional[str] = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                status = self._transport(api_key=self._api_key, payload=payload, timeout=self._timeout)
            except Exception as exc:  # noqa: BLE001 - class name only, never the message
                last_error = type(exc).__name__
                if attempt < self._max_attempts:
                    if self._backoff:
                        self._sleep(self._backoff)
                    continue
                self._degraded = True
                return self._fail(purpose, to_email, "DELIVERY_TIMEOUT", attempt, last_error)
            if 200 <= status < 300:
                return DeliveryAttempt(
                    provider=self.name,
                    purpose=purpose,
                    recipient_masked=mask_email(to_email),
                    delivered=True,
                    status="SENT",
                    attempts=attempt,
                )
            if status in (401, 403):
                self._degraded = True
                return self._fail(purpose, to_email, "AUTH_FAILED", attempt, f"http_{status}")
            if status == 429 or 500 <= status < 600:
                last_error = f"http_{status}"
                if attempt < self._max_attempts:
                    if self._backoff:
                        self._sleep(self._backoff)
                    continue
                self._degraded = True
                return self._fail(purpose, to_email, "DELIVERY_FAILED", attempt, last_error)
            # Other 4xx: permanent rejection, no retry.
            return self._fail(purpose, to_email, "DELIVERY_REJECTED", attempt, f"http_{status}")
        return self._fail(purpose, to_email, "DELIVERY_FAILED", self._max_attempts, last_error)

    def _fail(self, purpose: str, to_email: str, status: str, attempts: int, error_class: Optional[str]) -> DeliveryAttempt:
        return DeliveryAttempt(
            provider=self.name,
            purpose=purpose,
            recipient_masked=mask_email(to_email),
            delivered=False,
            status=status,
            attempts=attempts,
            error_class=error_class,
        )

    def send_verification_email(self, *, to_email: str, verify_link: str) -> DeliveryAttempt:
        subject, text, html = self._verification_body(verify_link)
        return self._send("email_verify", to_email, subject, text, html)

    def send_password_reset_email(self, *, to_email: str, reset_link: str) -> DeliveryAttempt:
        subject, text, html = self._reset_body(reset_link)
        return self._send("password_reset", to_email, subject, text, html)

    def health(self) -> dict[str, Any]:
        if not self.configured:
            return {"provider": self.name, "configured": False, "status": "NOT_CONFIGURED"}
        return {
            "provider": self.name,
            "configured": True,
            "status": "DEGRADED" if self._degraded else "READY",
        }


def build_email_provider(env: Optional[dict[str, str]] = None) -> EmailProvider:
    """Return the configured provider.

    * No provider name (or none/null/unset) -> NullEmailProvider (fail closed).
    * ``resend`` with both RESEND_API_KEY and NEXUS_EMAIL_FROM present ->
      ResendEmailProvider.
    * ``resend`` but missing key/from, or an unknown provider name -> a
      NullEmailProvider that reports NOT_CONFIGURED and never fabricates a send.
      It never silently falls back to a "successful" provider.
    """
    env = dict(os.environ if env is None else env)
    provider_name = (env.get("NEXUS_EMAIL_PROVIDER") or "").strip().lower()
    if not provider_name or provider_name in {"none", "null", "unset"}:
        return NullEmailProvider()
    if provider_name == "resend":
        api_key = (env.get("RESEND_API_KEY") or "").strip()
        from_address = (env.get("NEXUS_EMAIL_FROM") or "").strip()
        web_base_url = (env.get("NEXUS_PUBLIC_WEB_BASE_URL") or "").strip()
        if not api_key or not from_address or not web_base_url:
            # Named but not fully configured (key + sender + web base URL all
            # required) -> a Resend provider that reports configured=False /
            # status=NOT_CONFIGURED and fails closed (never a fabricated send),
            # while retaining the intended provider name for diagnostics.
            return ResendEmailProvider(api_key="", from_address="")
        return ResendEmailProvider(api_key=api_key, from_address=from_address)
    # Unknown provider name -> fail closed.
    return NullEmailProvider()
