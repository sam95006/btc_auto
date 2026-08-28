from __future__ import annotations

from typing import Any

import pytest

from backend.nexus_product_backend.email_provider import (
    NullEmailProvider,
    ResendEmailProvider,
    build_email_provider,
)

API_KEY = "rk_test_SECRETVALUE_should_never_leak"
FROM = "NEXUS <no-reply@mail.example>"
TO = "member@example.com"
VERIFY_LINK = "https://frontend.example/verify-email?token=RAW_TOKEN_SECRET"
RESET_LINK = "https://frontend.example/reset-password?token=RAW_RESET_SECRET"


class FakeTransport:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, api_key: str, payload: dict[str, Any], timeout: float) -> int:
        self.calls.append({"api_key": api_key, "payload": payload, "timeout": timeout})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return int(item)


def _provider(script: list[Any], **kw) -> tuple[ResendEmailProvider, FakeTransport]:
    transport = FakeTransport(script)
    provider = ResendEmailProvider(
        api_key=API_KEY,
        from_address=FROM,
        transport=transport,
        retry_backoff_seconds=0.0,
        **kw,
    )
    return provider, transport


def _audit_blob(attempt) -> str:
    return str(attempt.to_audit_dict())


def test_successful_verification_send() -> None:
    provider, transport = _provider([202])
    attempt = provider.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    assert attempt.delivered is True
    assert attempt.status == "SENT"
    assert attempt.attempts == 1
    payload = transport.calls[0]["payload"]
    assert payload["to"] == [TO]
    assert VERIFY_LINK in payload["text"] and VERIFY_LINK in payload["html"]
    assert provider.health()["status"] == "READY"


def test_successful_reset_send() -> None:
    provider, transport = _provider([200])
    attempt = provider.send_password_reset_email(to_email=TO, reset_link=RESET_LINK)
    assert attempt.delivered is True and attempt.status == "SENT"
    assert RESET_LINK in transport.calls[0]["payload"]["text"]


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_no_retry(status: int) -> None:
    provider, transport = _provider([status, 202])  # second would succeed if retried
    attempt = provider.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    assert attempt.delivered is False
    assert attempt.status == "AUTH_FAILED"
    assert attempt.attempts == 1
    assert len(transport.calls) == 1  # no retry on auth failure
    assert provider.health()["status"] == "DEGRADED"


def test_rate_limit_retries_then_succeeds() -> None:
    provider, transport = _provider([429, 202])
    attempt = provider.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    assert attempt.delivered is True
    assert attempt.attempts == 2
    assert len(transport.calls) == 2


def test_5xx_retries_then_succeeds() -> None:
    provider, transport = _provider([500, 502, 200])
    attempt = provider.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    assert attempt.delivered is True
    assert attempt.attempts == 3


def test_5xx_retry_exhaustion_fails_closed() -> None:
    provider, transport = _provider([500, 503, 500])
    attempt = provider.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    assert attempt.delivered is False
    assert attempt.status == "DELIVERY_FAILED"
    assert attempt.attempts == 3
    assert provider.health()["status"] == "DEGRADED"


def test_timeout_retries_then_succeeds() -> None:
    provider, transport = _provider([TimeoutError("t"), 202])
    attempt = provider.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    assert attempt.delivered is True
    assert attempt.attempts == 2


def test_timeout_exhaustion_fails_closed() -> None:
    provider, _ = _provider([TimeoutError("t"), TimeoutError("t"), TimeoutError("t")])
    attempt = provider.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    assert attempt.delivered is False
    assert attempt.status == "DELIVERY_TIMEOUT"


def test_other_4xx_permanent_no_retry() -> None:
    provider, transport = _provider([422, 202])
    attempt = provider.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    assert attempt.delivered is False
    assert attempt.status == "DELIVERY_REJECTED"
    assert len(transport.calls) == 1


def test_secret_and_link_never_in_audit_or_health() -> None:
    provider, _ = _provider([500, 500, 500])
    attempt = provider.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    blob = _audit_blob(attempt)
    assert API_KEY not in blob
    assert "RAW_TOKEN_SECRET" not in blob
    assert VERIFY_LINK not in blob
    assert TO not in blob  # recipient is masked
    health_blob = str(provider.health())
    assert API_KEY not in health_blob


def test_missing_config_fails_closed_not_null_success() -> None:
    # Named resend but missing key/from -> NullEmailProvider (fail closed).
    p1 = build_email_provider({"NEXUS_EMAIL_PROVIDER": "resend"})
    assert isinstance(p1, NullEmailProvider)
    a = p1.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    assert a.delivered is False
    # Directly constructing without config reports NOT_CONFIGURED and fails closed.
    bare = ResendEmailProvider(api_key="", from_address="")
    assert bare.configured is False
    b = bare.send_verification_email(to_email=TO, verify_link=VERIFY_LINK)
    assert b.delivered is False and b.status == "NOT_CONFIGURED"
    assert bare.health()["status"] == "NOT_CONFIGURED"


def test_unknown_provider_name_fails_closed() -> None:
    p = build_email_provider({"NEXUS_EMAIL_PROVIDER": "mailgun", "MAILGUN_API_KEY": "x"})
    assert isinstance(p, NullEmailProvider)


def test_factory_builds_configured_resend_provider() -> None:
    p = build_email_provider(
        {
            "NEXUS_EMAIL_PROVIDER": "resend",
            "RESEND_API_KEY": API_KEY,
            "NEXUS_EMAIL_FROM": FROM,
        }
    )
    assert isinstance(p, ResendEmailProvider)
    assert p.configured is True
    assert p.name == "resend"
    assert p.health()["status"] == "READY"
