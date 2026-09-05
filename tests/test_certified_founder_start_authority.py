"""Founder Private DEMO RUNTIME REPAIR 1 — certified one-shot start authority.

Proves the certified bounded 6H runtime bootstraps from SIGNED one-shot Founder
authorization (verified signed request + validated lease + consumed founder-auth
marker + Demo-only invariants) WITHOUT any FOUNDER_6H_APPROVED env, while the
LEGACY engine still requires its env approval UNCHANGED (the frozen
nexus_demo_execution engine is not modified). Offline; no network; no orders.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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

HEX_A = "a" * 40
HEX_B = "b" * 40


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
