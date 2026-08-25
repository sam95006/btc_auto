from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.nexus_bounded_runtime.bounded_start_auth import (
    SHORT_FOUNDER_PHRASE,
    sign_bounded_start_request,
    verify_bounded_start_request,
)
from backend.nexus_bounded_runtime.certified_short_session import (
    SHORT_MAX_DURATION_SEC,
    SHORT_SESSION_ID_PREFIX,
    CertifiedShortBoundedSession,
)
from backend.nexus_bounded_runtime.runtime_lease import RuntimeLease, validate_runtime_lease
from backend.nexus_demo_execution import SERVICE_NAME
from backend.nexus_demo_execution.bounded_autonomous_engine import BoundedAutonomousSessionEngine
from tools.ci.demo_bounded_session_lease import FOUNDER_PHRASE, create_lease

TEST_SHA = "d287463f929795c2a3db2ee8fa4e0091a3cb4287"
TEST_SECRET = "runtime-lease-service-binding-test-secret"
WRONG_SERVICE_NAME = "nexus-member-preview-v18-2-1"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _short_lease(*, seconds: int = SHORT_MAX_DURATION_SEC, **overrides: object) -> dict[str, object]:
    start = overrides.pop("authorized_at_dt", _now())
    assert isinstance(start, datetime)
    payload: dict[str, object] = {
        "session_id": f"{SHORT_SESSION_ID_PREFIX}{start.strftime('%Y%m%dT%H%M%SZ')}-svcbind1",
        "authorized_at": _fmt(start),
        "expires_at": _fmt(start + timedelta(seconds=seconds)),
        "exchange": "BYBIT_DEMO",
        "mainnet": False,
        "real_money": False,
        "expected_runtime_sha": TEST_SHA,
        "service_name": SERVICE_NAME,
    }
    payload.update(overrides)
    return payload


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(key, "false")
    monkeypatch.setenv("GITHUB_SHA", TEST_SHA)


def _signed_short_body(
    monkeypatch: pytest.MonkeyPatch,
    lease: dict[str, object] | None = None,
) -> dict[str, object]:
    _disarm(monkeypatch)
    monkeypatch.setenv("NEXUS_BOUNDED_SESSION_CONTROL_SECRET", TEST_SECRET)
    monkeypatch.setenv("FOUNDER_GATE", "DEMO_CERTIFIED_SHORT_BOUNDED_V1")
    monkeypatch.setenv("FOUNDER_SHORT_BOUNDED_APPROVED", "true")
    return sign_bounded_start_request(
        lease=lease or _short_lease(),
        founder_phrase=SHORT_FOUNDER_PHRASE,
        secret=TEST_SECRET,
    )


def _session(tmp_path: Path) -> CertifiedShortBoundedSession:
    return CertifiedShortBoundedSession(
        gate=MagicMock(),
        reader=MagicMock(),
        persistence=MagicMock(),
        epoch_tracker=MagicMock(),
        kill_switch=MagicMock(engaged=False),
        writer=MagicMock(),
        approval=MagicMock(),
        export_dir=tmp_path,
        data_root=tmp_path,
    )


def _validate_short(payload: dict[str, object]) -> dict[str, object]:
    return validate_runtime_lease(
        RuntimeLease.from_dict(payload),
        session_id_prefix=SHORT_SESSION_ID_PREFIX,
        max_duration_sec=SHORT_MAX_DURATION_SEC,
    )


def test_runtime_lease_requires_explicit_validation_service_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    correct = _validate_short(_short_lease())
    assert correct["ok"] is True

    missing_payload = _short_lease()
    missing_payload.pop("service_name")
    missing = _validate_short(missing_payload)
    assert missing["ok"] is False
    assert missing["reason"] == "runtime_lease_service_name_missing"

    empty = _validate_short(_short_lease(service_name=""))
    assert empty["ok"] is False
    assert empty["reason"] == "runtime_lease_service_name_missing"

    wrong = _validate_short(_short_lease(service_name=WRONG_SERVICE_NAME))
    assert wrong["ok"] is False
    assert wrong["reason"] == "runtime_lease_service_name_mismatch"


def test_signed_wrong_service_request_signature_valid_but_runtime_lease_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrong_service = _short_lease(service_name=WRONG_SERVICE_NAME)
    body = _signed_short_body(monkeypatch, wrong_service)

    verified = verify_bounded_start_request(body, expected_founder_phrase=SHORT_FOUNDER_PHRASE)
    rejected = _validate_short(body["lease"])  # type: ignore[arg-type]

    assert verified["ok"] is True
    assert rejected["ok"] is False
    assert rejected["reason"] == "runtime_lease_service_name_mismatch"


def test_wrong_service_fails_before_durable_claim_run_loop_and_exchange_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import backend.nexus_bounded_runtime.bootstrap as bootstrap

    base_start = MagicMock(return_value={"ok": True, "status": "STARTING"})
    monkeypatch.setattr(bootstrap, "CERTIFIED_BOUNDED_RUNTIME_ACTIVE", True)
    monkeypatch.setattr(BoundedAutonomousSessionEngine, "start", base_start)
    body = _signed_short_body(monkeypatch, _short_lease(service_name=WRONG_SERVICE_NAME))
    session = _session(tmp_path)
    session._ensure_certified_stores = MagicMock()
    session._durable_lease_store = MagicMock()
    session._durable_lease_store.claim_or_resume.return_value = {"ok": True}

    result = session.start(start_request=body)

    assert result["ok"] is False
    assert result["reason"] == "runtime_lease_service_name_mismatch"
    session._durable_lease_store.claim_or_resume.assert_not_called()
    session._ensure_certified_stores.assert_not_called()
    base_start.assert_not_called()
    session.writer.create_market_order.assert_not_called()
    assert session._state["order_intent_total"] == 0
    assert session._state["exchange_request_total"] == 0


def test_canonical_6h_payload_and_short_expected_payload_include_service_name() -> None:
    six = create_lease(founder_phrase=FOUNDER_PHRASE, expected_runtime_sha=TEST_SHA)
    assert six.to_runtime_payload()["service_name"] == SERVICE_NAME
    assert _short_lease()["service_name"] == SERVICE_NAME


def test_existing_runtime_lease_fail_closed_checks_remain(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)

    bad_sha = _validate_short(_short_lease(expected_runtime_sha="0" * 40))
    assert bad_sha["reason"] == "runtime_sha_mismatch"

    mainnet = _validate_short(_short_lease(mainnet=True))
    assert mainnet["reason"] == "runtime_lease_mainnet_or_real_money"

    real_money = _validate_short(_short_lease(real_money=True))
    assert real_money["reason"] == "runtime_lease_mainnet_or_real_money"

    wrong_prefix = _validate_short(_short_lease(session_id="NEXUS-DEMO-6H-V2-20260101T000000Z-svcbind1"))
    assert wrong_prefix["reason"] == "runtime_session_id_prefix_mismatch"

    too_long = _validate_short(_short_lease(seconds=SHORT_MAX_DURATION_SEC + 1))
    assert too_long["reason"] == "runtime_lease_duration_exceeds_scope"
