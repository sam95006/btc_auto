"""Pre-live bounded 6H runtime hardening — signed start, SHA, learning, submit-unknown."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.nexus_bounded_runtime.bootstrap import (
    certified_bounded_runtime_active,
    install_certified_bounded_runtime,
)
from backend.nexus_bounded_runtime.bounded_start_auth import sign_bounded_start_request, verify_bounded_start_request
from backend.nexus_bounded_runtime.certified_learning import validate_exchange_outcome_evidence, write_durable_lesson_from_trade
from backend.nexus_bounded_runtime.certified_session import CertifiedBounded6HSession
from backend.nexus_bounded_runtime.durable_lease_store import DurableLeaseStore
from backend.nexus_bounded_runtime.runtime_lease import validate_runtime_sha
from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.p2_run8_durable_loader import PNL_PROVENANCE
from tools.ci.bounded_runtime_pre_live_hardening import prove_control_plane_independence, run as run_pre_live
from tools.ci.demo_bounded_session_lease import FOUNDER_PHRASE, create_lease
from tools.ci.p2_historical_p1_p2_regression_lock import HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES

_TEST_SHA = "dc98088eed40f7b6f599f0c06c593f8b736cea89"
_TEST_SECRET = "test-bounded-control-secret-not-for-production"


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(key, "false")


def test_full_runtime_sha_fail_closed() -> None:
    assert validate_runtime_sha(expected=_TEST_SHA, deployed=_TEST_SHA)["ok"] is True
    assert validate_runtime_sha(expected="", deployed=_TEST_SHA)["ok"] is False
    assert validate_runtime_sha(expected=_TEST_SHA, deployed="")["ok"] is False
    assert validate_runtime_sha(expected=_TEST_SHA[:7], deployed=_TEST_SHA)["ok"] is False


def test_signed_start_request_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv("NEXUS_BOUNDED_SESSION_CONTROL_SECRET", _TEST_SECRET)
    lease = create_lease(founder_phrase=FOUNDER_PHRASE, expected_runtime_sha=_TEST_SHA)
    signed = sign_bounded_start_request(lease=lease.to_runtime_payload(), secret=_TEST_SECRET)
    verified = verify_bounded_start_request(signed)
    assert verified["ok"] is True
    assert verified.get("founder_authorization_one_shot") is True


def test_control_plane_independence_not_boolean_echo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv("NEXUS_BOUNDED_SESSION_CONTROL_SECRET", _TEST_SECRET)
    monkeypatch.setenv("GITHUB_SHA", _TEST_SHA)
    lease_root = Path("artifacts/test_pre_live_lease_independence")
    proof = prove_control_plane_independence(lease_root=lease_root)
    assert proof["TRANSIENT_ZEABUR_ENV_RUNTIME_AUTHORITY_REMOVED"] is True
    assert proof["ACTIVE_SESSION_SURVIVES_CONTROL_PLANE_DISARM"] is True
    store = DurableLeaseStore(lease_root)
    assert store.load() is not None


def test_learning_rejects_synthetic_defaults() -> None:
    writer = MagicMock()
    writer.list_closed_pnl.return_value = []
    result = validate_exchange_outcome_evidence(
        writer=writer,
        active={"symbol": "BTCUSDT", "side": "Buy", "trade_id": "t1", "decision_id": "d1"},
        pnl={"net_pnl": "-1", "pnl_provenance": PNL_PROVENANCE},
    )
    assert result.get("ok") is False
    assert result.get("reason") == "LEARNING_CLOSURE_HOLD"


def test_learning_requires_exact_close_order_id_match() -> None:
    writer = MagicMock()
    writer.list_closed_pnl.return_value = [
        {"orderId": "close-123", "avgEntryPrice": "1", "avgExitPrice": "1", "qty": "0.001"}
    ]
    result = write_durable_lesson_from_trade(
        store=MagicMock(),
        writer=writer,
        active={
            "symbol": "BTCUSDT",
            "side": "Buy",
            "trade_id": "t1",
            "decision_id": "d1",
            "close_order_id": "close-999",
            "entry_order_id": "entry-1",
            "actual_entry_price": "1",
            "actual_exit_price": "1",
            "qty": "0.001",
        },
        pnl={
            "net_pnl": "-0.07",
            "pnl_provenance": PNL_PROVENANCE,
            "entry_fee": "0.03",
            "exit_fee": "0.03",
        },
    )
    assert result.get("ok") is False


def test_certified_start_requires_signed_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv("GITHUB_SHA", _TEST_SHA)
    install_certified_bounded_runtime()
    session = CertifiedBounded6HSession(
        gate=MagicMock(),
        reader=MagicMock(),
        persistence=MagicMock(),
        epoch_tracker=MagicMock(),
        kill_switch=MagicMock(),
        writer=MagicMock(),
        approval=MagicMock(),
        export_dir=Path("."),
        data_root=Path("."),
    )
    assert session.start(start_request=None).get("ok") is False


def test_bootstrap_fail_closed_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    install_certified_bounded_runtime()
    assert certified_bounded_runtime_active() is True


def test_pre_live_qualification_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    evidence = run_pre_live(
        sqlite_path=tmp_path / "q.db",
        lease_root=Path("artifacts/test_pre_live_exit_lease"),
    )
    assert evidence["FINAL_BOUNDED_6H_EXIT_LIFECYCLE_PASS"] is True
    assert evidence["FINAL_BOUNDED_RUNTIME_PRELIVE_HARDENING_PASS"] is True
    assert evidence["CREATE_ORDER_CALLS"] == 0
    assert evidence["EXCHANGE_WRITE_CALL_COUNT"] == 0
    assert evidence["DURABLE_LEASE_STORAGE_PREFLIGHT_PASS"] is True


def test_ephemeral_lease_storage_rejected() -> None:
    from backend.nexus_bounded_runtime.durable_lease_store import validate_durable_lease_storage_path

    ephemeral = validate_durable_lease_storage_path("/tmp/nexus_lease_test")
    assert ephemeral["DURABLE_LEASE_STORAGE_PREFLIGHT_PASS"] is False
    durable = validate_durable_lease_storage_path("artifacts/lease_probe")
    assert durable["DURABLE_LEASE_STORAGE_PREFLIGHT_PASS"] is True
    assert durable["EPHEMERAL_LEASE_STORAGE_REJECTED"] is True


def test_wiring_markers_include_exit_lifecycle() -> None:
    from backend.nexus_bounded_runtime.certified_session import wiring_markers

    markers = wiring_markers()
    assert markers["BOUNDED_RUNTIME_DURABLE_EXIT_LEDGER_AUTHORITY"] is True
    assert markers["NO_FIRST_REDUCEONLY_CLOSE_FALLBACK"] is True
    assert markers["PNL_PROVENANCE_FROM_RECONCILIATION"] is True


def test_regression_lock_includes_pre_live_hardening_test() -> None:
    assert "tests/test_bounded_runtime_pre_live_hardening.py" in HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES
