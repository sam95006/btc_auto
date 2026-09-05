"""Founder Private DEMO RUNTIME REPAIR 1 — certified one-shot start authority.

Proves the certified bounded 6H runtime starts from SIGNED one-shot Founder
authorization (verified signed request + validated lease + correct runtime SHA +
consumed founder-auth marker + Demo-only invariants) WITHOUT any
FOUNDER_6H_APPROVED env, exercised through the REAL CertifiedBounded6HSession.
start() entry path (external deps — store/reconciliation, lease store, worker
thread — mocked; the signed request and lease are NOT bypassed).

This repair extracts a single minimal, overridable authorization hook in the
shared bounded engine (backend/nexus_demo_execution/bounded_autonomous_engine.py);
legacy env-gated behavior is preserved byte-for-byte, and that one authorized
change is re-frozen via an advanced freeze baseline (test_p2_certified_surface_
freeze). Offline; no network; no orders.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import backend.nexus_bounded_runtime.bootstrap as bootstrap
from backend.nexus_bounded_runtime.bounded_start_auth import (
    sign_bounded_start_request,
    verify_bounded_start_request,
)
from backend.nexus_bounded_runtime.certified_session import CertifiedBounded6HSession
from backend.nexus_bounded_runtime.runtime_lease import (
    SERVICE_NAME,
    RuntimeLease,
    validate_runtime_lease,
)
from backend.nexus_demo_execution.bounded_autonomous_engine import BoundedAutonomousSessionEngine
from backend.nexus_demo_execution.session_policy import policy_6h_v2
from backend.nexus_demo_execution.v2_policy import SESSION_GATE_NAME as V2_GATE
from tools.ci.demo_bounded_session_lease import FOUNDER_PHRASE

HEX_A = "a" * 40
HEX_B = "b" * 40
TEST_SHA = "d287463f929795c2a3db2ee8fa4e0091a3cb4287"
TEST_SECRET = "repair1-test-secret-not-production"


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _6h_lease(**over) -> dict:
    start = _now()
    payload = {
        "session_id": f"NEXUS-DEMO-6H-V2-{start.strftime('%Y%m%dT%H%M%SZ')}-abc12345",
        "authorized_at": _fmt(start),
        "expires_at": _fmt(start + timedelta(hours=5)),
        "exchange": "BYBIT_DEMO",
        "mainnet": False,
        "real_money": False,
        "expected_runtime_sha": TEST_SHA,
        "service_name": SERVICE_NAME,
    }
    payload.update(over)
    return payload


def _signed_6h(monkeypatch, lease: dict | None = None) -> dict:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(key, "false")
    monkeypatch.setenv("GITHUB_SHA", TEST_SHA)  # deployed runtime SHA == lease expected
    monkeypatch.setenv("NEXUS_BOUNDED_SESSION_CONTROL_SECRET", TEST_SECRET)
    monkeypatch.setenv("FOUNDER_GATE", V2_GATE)
    monkeypatch.setenv("FOUNDER_6H_APPROVED", "false")  # env explicitly OFF for every start() test
    return sign_bounded_start_request(lease=lease or _6h_lease(), founder_phrase=FOUNDER_PHRASE, secret=TEST_SECRET)


def _cert_session(tmp_path):
    """A certified 6H session with ONLY external deps mocked (Postgres store,
    reconciliation, durable lease store, worker thread). The signed request and
    lease are NOT bypassed; _founder_auth_consumed / _runtime_lease are NOT
    pre-populated — start() must establish them from the signed request."""
    s = _mk(CertifiedBounded6HSession, tmp_path)
    s._ensure_certified_stores = MagicMock()  # no Postgres / reconciliation
    s._durable_lease_store = MagicMock()
    s._durable_lease_store.claim_or_resume.return_value = {"ok": True}
    return s


# --------------------------------------------------------------------------- #
# BLOCKER 1: REAL certified start() entry path, FOUNDER_6H_APPROVED=false.
# --------------------------------------------------------------------------- #
def test_real_certified_start_supersedes_env_reaches_starting(monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap, "CERTIFIED_BOUNDED_RUNTIME_ACTIVE", True)
    body = _signed_6h(monkeypatch)
    s = _cert_session(tmp_path)
    assert s._founder_auth_consumed is False  # not pre-populated
    assert s._runtime_lease is None
    result = s.start(start_request=body)
    assert result.get("ok") is True, result
    assert result.get("reason") != "founder_not_approved"
    assert result.get("status") == "STARTING"
    assert result.get("founder_authorization_one_shot") is True
    assert result.get("certified_runtime") is True
    # start() itself established the one-shot authorization from the signed request.
    assert s._founder_auth_consumed is True and s._runtime_lease is not None


def test_real_certified_start_missing_signed_request_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap, "CERTIFIED_BOUNDED_RUNTIME_ACTIVE", True)
    _signed_6h(monkeypatch)  # sets env, but we pass no body
    result = _cert_session(tmp_path).start(start_request=None)
    assert result.get("ok") is False and result.get("reason") == "start_request_missing"


def test_real_certified_start_bad_signature_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap, "CERTIFIED_BOUNDED_RUNTIME_ACTIVE", True)
    body = _signed_6h(monkeypatch)
    body["signature"] = "f" * 64
    result = _cert_session(tmp_path).start(start_request=body)
    assert result.get("ok") is False and result.get("reason") == "signature_mismatch"


def test_real_certified_start_expired_lease_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap, "CERTIFIED_BOUNDED_RUNTIME_ACTIVE", True)
    past = _now() - timedelta(hours=1)
    lease = _6h_lease(authorized_at=_fmt(past - timedelta(hours=5)), expires_at=_fmt(past))
    body = _signed_6h(monkeypatch, lease)
    result = _cert_session(tmp_path).start(start_request=body)
    assert result.get("ok") is False and result.get("reason") == "runtime_lease_expired"


def test_real_certified_start_wrong_runtime_sha_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap, "CERTIFIED_BOUNDED_RUNTIME_ACTIVE", True)
    body = _signed_6h(monkeypatch, _6h_lease(expected_runtime_sha=HEX_A))  # != GITHUB_SHA (TEST_SHA)
    result = _cert_session(tmp_path).start(start_request=body)
    assert result.get("ok") is False and result.get("reason") == "runtime_sha_mismatch"


@pytest.mark.parametrize("field", ["mainnet", "real_money"])
def test_real_certified_start_lease_mainnet_or_real_money_blocked(monkeypatch, tmp_path, field):
    monkeypatch.setattr(bootstrap, "CERTIFIED_BOUNDED_RUNTIME_ACTIVE", True)
    body = _signed_6h(monkeypatch, _6h_lease(**{field: True}))
    result = _cert_session(tmp_path).start(start_request=body)
    assert result.get("ok") is False and result.get("reason") == "runtime_lease_mainnet_or_real_money"


@pytest.mark.parametrize("flag", ["MAINNET", "REAL_MONEY"])
def test_real_certified_start_env_mainnet_or_real_money_blocked(monkeypatch, tmp_path, flag):
    monkeypatch.setattr(bootstrap, "CERTIFIED_BOUNDED_RUNTIME_ACTIVE", True)
    body = _signed_6h(monkeypatch)
    monkeypatch.setenv(flag, "true")  # process-level demo invariant violation
    result = _cert_session(tmp_path).start(start_request=body)
    assert result.get("ok") is False and result.get("reason") == "demo_only_invariant_violated"


def _mk(cls, tmp_path: Path, **extra):
    obj = cls(
        gate=MagicMock(),
        reader=MagicMock(),
        persistence=MagicMock(),
        epoch_tracker=MagicMock(),
        kill_switch=MagicMock(engaged=False),
        writer=MagicMock(),
        approval=MagicMock(),
        export_dir=tmp_path,
        data_root=tmp_path,
        **extra,
    )
    obj._safe_run = lambda: None  # type: ignore[assignment]  # neutralize worker thread
    return obj


def _certified(tmp_path, *, consumed=True):
    s = _mk(CertifiedBounded6HSession, tmp_path)
    s._founder_auth_consumed = consumed
    s._runtime_lease = MagicMock(session_id="NEXUS-DEMO-6H-V2-unit") if consumed else None
    return s


# --------------------------------------------------------------------------- #
# The repair: the certified override supersedes FOUNDER_6H_APPROVED at the exact
# engine.start() boundary that previously returned founder_not_approved.
# --------------------------------------------------------------------------- #
def test_certified_authorization_supersedes_founder_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDER_GATE", V2_GATE)
    monkeypatch.setenv("FOUNDER_6H_APPROVED", "false")  # env explicitly OFF
    monkeypatch.delenv("MAINNET", raising=False)
    monkeypatch.delenv("REAL_MONEY", raising=False)
    s = _certified(tmp_path, consumed=True)
    # Drive the exact engine boundary that enforced founder_not_approved. The
    # certified _founder_start_authorization override runs inside it.
    result = BoundedAutonomousSessionEngine.start(s)
    assert result.get("ok") is True, result
    assert result.get("reason") != "founder_not_approved"
    assert result.get("status") == "STARTING"


def test_certified_without_one_shot_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDER_GATE", V2_GATE)
    monkeypatch.setenv("FOUNDER_6H_APPROVED", "false")
    s = _certified(tmp_path, consumed=False)
    result = BoundedAutonomousSessionEngine.start(s)
    assert result.get("ok") is False
    assert result.get("reason") == "certified_founder_authorization_missing"


def test_certified_preserves_founder_gate_check(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDER_GATE", "WRONG_GATE_LABEL")
    s = _certified(tmp_path, consumed=True)
    result = BoundedAutonomousSessionEngine.start(s)
    assert result.get("ok") is False and result.get("reason") == "founder_gate_mismatch"


@pytest.mark.parametrize("flag", ["MAINNET", "REAL_MONEY"])
def test_certified_authorization_blocks_mainnet_and_real_money(monkeypatch, tmp_path, flag):
    monkeypatch.setenv("FOUNDER_GATE", V2_GATE)
    monkeypatch.setenv("FOUNDER_6H_APPROVED", "false")
    monkeypatch.setenv(flag, "true")
    s = _certified(tmp_path, consumed=True)
    result = BoundedAutonomousSessionEngine.start(s)
    assert result.get("ok") is False and result.get("reason") == "demo_only_invariant_violated"


# --------------------------------------------------------------------------- #
# Legacy engine behavior preserved EXACTLY (only an overridable hook was added).
# --------------------------------------------------------------------------- #
def test_legacy_engine_still_requires_founder_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDER_GATE", V2_GATE)
    monkeypatch.setenv("FOUNDER_6H_APPROVED", "false")
    e = _mk(BoundedAutonomousSessionEngine, tmp_path, policy=policy_6h_v2())
    result = e.start()
    assert result.get("ok") is False and result.get("reason") == "founder_not_approved"


def test_legacy_engine_starts_with_founder_env_true(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDER_GATE", V2_GATE)
    monkeypatch.setenv("FOUNDER_6H_APPROVED", "true")
    e = _mk(BoundedAutonomousSessionEngine, tmp_path, policy=policy_6h_v2())
    result = e.start()
    assert result.get("ok") is True and result.get("status") == "STARTING"


# --------------------------------------------------------------------------- #
# Signed request + lease validation still block the certified start path.
# --------------------------------------------------------------------------- #
def test_missing_signed_request_blocked():
    assert verify_bounded_start_request(None)["reason"] == "start_request_missing"


def test_bad_signature_blocked(monkeypatch):
    monkeypatch.setenv("NEXUS_BOUNDED_SESSION_CONTROL_SECRET", "unit-test-secret")
    lease = {"session_id": "NEXUS-DEMO-6H-V2-x", "authorized_at": "2026-01-01T00:00:00Z",
             "expires_at": "2026-01-01T06:00:00Z", "exchange": "BYBIT_DEMO",
             "mainnet": False, "real_money": False, "expected_runtime_sha": HEX_A,
             "service_name": SERVICE_NAME}
    signed = sign_bounded_start_request(lease=lease)
    signed["signature"] = "f" * 64
    assert verify_bounded_start_request(signed)["reason"] == "signature_mismatch"


def _lease(**over) -> RuntimeLease:
    base = dict(
        session_id="NEXUS-DEMO-6H-V2-unit", authorized_at="2026-09-01T00:00:00Z",
        expires_at="2999-01-01T00:00:00Z", exchange="BYBIT_DEMO", mainnet=False,
        real_money=False, expected_runtime_sha=HEX_A, service_name=SERVICE_NAME,
    )
    base.update(over)
    return RuntimeLease(**base)


def test_expired_lease_blocked():
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert validate_runtime_lease(_lease(expires_at=past))["reason"] == "runtime_lease_expired"


def test_wrong_runtime_sha_blocked(monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", HEX_B)
    assert validate_runtime_lease(_lease(expected_runtime_sha=HEX_A))["reason"] == "runtime_sha_mismatch"


def test_lease_mainnet_or_real_money_blocked():
    assert validate_runtime_lease(_lease(mainnet=True))["reason"] == "runtime_lease_mainnet_or_real_money"
    assert validate_runtime_lease(_lease(real_money=True))["reason"] == "runtime_lease_mainnet_or_real_money"
