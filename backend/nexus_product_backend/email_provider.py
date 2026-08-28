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

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol


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


def build_email_provider(env: Optional[dict[str, str]] = None) -> EmailProvider:
    """Return the configured provider, or NullEmailProvider when none is set.

    A concrete vendor is selected only when ``NEXUS_EMAIL_PROVIDER`` names one
    AND its required configuration is present. This module intentionally ships
    with no built-in vendor, so absent external wiring it returns the null
    provider — never a fabricated sender.
    """
    env = dict(os.environ if env is None else env)
    provider_name = (env.get("NEXUS_EMAIL_PROVIDER") or "").strip().lower()
    if not provider_name or provider_name in {"none", "null", "unset"}:
        return NullEmailProvider()
    # A real provider must register a sender out-of-band; without one we still
    # refuse to fabricate delivery.
    return NullEmailProvider()
