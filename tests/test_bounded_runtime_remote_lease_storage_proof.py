"""Remote durable lease storage proof — runtime authority, not GitHub runner."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.nexus_bounded_runtime.runtime_lease_storage_proof import (
    consume_remote_storage_proof,
    prove_runtime_durable_lease_storage,
    redact_storage_path,
    resolve_bounded_lease_root,
)
from tools.ci.demo_bounded_session_preflight import run_preflight
from tools.ci.p2_historical_p1_p2_regression_lock import HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES
from tools.ci.remote_durable_lease_storage_proof import prove_local_runner_not_authoritative, run as run_remote_proof


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(key, "false")


def test_github_runner_tmp_not_authoritative() -> None:
    proof = prove_local_runner_not_authoritative()
    assert proof["GITHUB_RUNNER_TMP_NOT_AUTHORITATIVE"] is True
    assert proof["GITHUB_RUNNER_TMP_EPHEMERAL"] is True


def test_runtime_proof_reports_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    root = Path("artifacts/test_runtime_lease_proof_data").resolve()
    monkeypatch.setenv("NEXUS_DATA_ROOT", str(root))
    proof = prove_runtime_durable_lease_storage(root)
    assert "DURABLE_LEASE_STORAGE_RUNTIME_PROVEN" in proof
    assert "DURABLE_LEASE_STORAGE_PATH" in proof
    assert proof["EPHEMERAL_LEASE_STORAGE"] is False
    assert proof["DURABLE_LEASE_STORAGE_RUNTIME_PROVEN"] is True
    assert "bounded_runtime_lease" in proof["DURABLE_LEASE_STORAGE_PATH"]


def test_consume_remote_storage_proof_requires_validation_runtime_source() -> None:
    ok = consume_remote_storage_proof(
        {
            "DURABLE_LEASE_STORAGE_RUNTIME_PROVEN": True,
            "EPHEMERAL_LEASE_STORAGE": False,
            "RUNTIME_STORAGE_PROOF_SOURCE": "validation_runtime",
        }
    )
    bad = consume_remote_storage_proof(
        {
            "DURABLE_LEASE_STORAGE_RUNTIME_PROVEN": True,
            "EPHEMERAL_LEASE_STORAGE": False,
            "RUNTIME_STORAGE_PROOF_SOURCE": "github_runner",
        }
    )
    assert ok["RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER"] is True
    assert bad["RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER"] is False


def test_offline_preflight_uses_runtime_proof_not_runner_tmp(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv("NEXUS_DATA_ROOT", str(Path("artifacts/test_preflight_runtime_data").resolve()))
    report = run_preflight(offline=True, founder_phrase="START_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION")
    assert report["checks"]["DURABLE_LEASE_STORAGE_RUNTIME_PROVEN"] is True
    assert report["checks"]["EPHEMERAL_LEASE_STORAGE"] is False


def test_remote_preflight_requires_validation_service_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    remote_status = {
        "bounded_6h": {
            "status": "IDLE",
            "found": False,
            "CERTIFIED_BOUNDED_RUNTIME_ACTIVE": True,
            "DURABLE_LEASE_STORAGE_RUNTIME_PROVEN": True,
            "DURABLE_LEASE_STORAGE_PATH": "/app/data/nexus_demo_validation/artifacts/bounded_runtime_lease/6H_V2",
            "EPHEMERAL_LEASE_STORAGE": False,
            "NEXUS_DATA_ROOT": "/app/data/nexus_demo_validation",
            "RUNTIME_STORAGE_PROOF_SOURCE": "validation_runtime",
        }
    }

    def _fake_get(url: str):
        if "bounded-6h/status" in url:
            return remote_status, 200
        if url.endswith("/health"):
            return {"github_sha": os.environ.get("GITHUB_SHA", "a" * 40)}, 200
        return {}, 200

    with patch("tools.ci.demo_bounded_session_preflight._get", side_effect=_fake_get):
        with patch("tools.ci.demo_6h_v2_preflight.run_preflight", return_value={"6h_v2_ready": True, "http": {"health": 200}, "position_count": 0, "open_order_count": 0}):
            report = run_preflight(
                base_url="https://example.test",
                expected_github_sha="a" * 40,
                offline=False,
                postgres_url="",
            )
    assert report["checks"]["RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER"] is True
    assert report["checks"]["DURABLE_LEASE_STORAGE_PREFLIGHT_PASS"] is True
    assert report["REMOTE_DURABLE_LEASE_STORAGE_PROOF_PASS"] is True


def test_remote_preflight_holds_without_runtime_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)

    def _fake_get(url: str):
        if "bounded-6h/status" in url:
            return {"bounded_6h": {"status": "IDLE", "CERTIFIED_BOUNDED_RUNTIME_ACTIVE": True}}, 200
        return {"github_sha": "b" * 40}, 200

    with patch("tools.ci.demo_bounded_session_preflight._get", side_effect=_fake_get):
        with patch("tools.ci.demo_6h_v2_preflight.run_preflight", return_value={"6h_v2_ready": True, "http": {"health": 200}, "position_count": 0, "open_order_count": 0}):
            report = run_preflight(base_url="https://example.test", offline=False)
    assert report["preflight_pass"] is False
    assert "runtime_durable_lease_storage_not_proven" in report["problems"]


def test_remote_qualification_offline_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv("NEXUS_DATA_ROOT", str(Path("artifacts/remote_lease_storage_qual").resolve()))
    evidence = run_remote_proof(offline=True)
    assert evidence["REMOTE_DURABLE_LEASE_STORAGE_PROOF_PASS"] is True
    assert evidence["CREATE_ORDER_CALLS"] == 0


def test_regression_lock_includes_remote_lease_storage_test() -> None:
    assert "tests/test_bounded_runtime_remote_lease_storage_proof.py" in HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES
