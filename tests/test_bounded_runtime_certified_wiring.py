"""Bounded 6H runtime certified P1/P2 surface wiring — structural and integration proof."""
from __future__ import annotations

import inspect
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.nexus_bounded_runtime.bootstrap import certified_bounded_runtime_active, install_certified_bounded_runtime
from backend.nexus_bounded_runtime.bounded_start_auth import sign_bounded_start_request, verify_bounded_start_request
from backend.nexus_bounded_runtime.certified_session import CertifiedBounded6HSession, wiring_markers
from backend.nexus_bounded_runtime.runtime_lease import RuntimeLease, validate_runtime_lease, validate_runtime_sha
from backend.nexus_demo_execution.bounded_autonomous_engine import BoundedAutonomousSessionEngine
from tools.ci.bounded_runtime_integration_qualification import run as run_integration_qual
from tools.ci.demo_bounded_session_lease import FOUNDER_PHRASE, create_lease
from tools.ci.p2_historical_p1_p2_regression_lock import HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES

ROOT = Path(__file__).resolve().parents[1]
FROZEN_ENGINE = ROOT / "backend/nexus_demo_execution/bounded_autonomous_engine.py"
MIGRATION_0007 = ROOT / "backend/nexus_persistence_pg/migrations/0007_p2_research_learning_store.sql"
_TEST_SHA = "dc98088eed40f7b6f599f0c06c593f8b736cea89"
_TEST_SECRET = "test-bounded-control-secret-not-for-production"


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(key, "false")


def test_bootstrap_replaces_bounded_6h_session_class() -> None:
    install_certified_bounded_runtime()
    import backend.nexus_demo_execution.bounded_6h_session as mod

    assert mod.Bounded6HSession is CertifiedBounded6HSession
    assert certified_bounded_runtime_active() is True


def test_frozen_engine_still_has_legacy_session_memory_guard() -> None:
    source = FROZEN_ENGINE.read_text(encoding="utf-8")
    entry = source.split("def _try_entry")[1].split("def _record_exit")[0]
    assert "self.memory.apply" in entry
    assert "create_market_order" in entry
    assert entry.index("self.memory.apply") < entry.index("create_market_order")


def test_certified_session_persist_before_submit_not_session_memory_policy() -> None:
    source = inspect.getsource(CertifiedBounded6HSession._try_entry)
    assert "evaluate_certified_guard" in source
    assert "persist_durable_intent" in source
    assert "submit_after_persist" in source
    assert source.index("evaluate_certified_guard") < source.index("persist_durable_intent")
    assert source.index("persist_durable_intent") < source.index("submit_after_persist")
    assert "session_mistake_telemetry" in source
    assert "evaluate_certified_entry_risk" in source


def test_certified_session_requires_signed_start_at_start() -> None:
    source = inspect.getsource(CertifiedBounded6HSession.start)
    assert "verify_bounded_start_request" in source
    assert "validate_runtime_lease" in source
    assert "self.session_id = lease.session_id" in source


def test_wiring_markers_all_true() -> None:
    markers = wiring_markers()
    assert all(markers.values()), markers


def test_runtime_rejects_missing_and_expired_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    assert validate_runtime_lease(None)["ok"] is False
    lease = create_lease(founder_phrase=FOUNDER_PHRASE, expected_runtime_sha=_TEST_SHA)
    expired = RuntimeLease(
        session_id=lease.session_id,
        authorized_at=lease.authorized_at,
        expires_at="2000-01-01T00:00:00Z",
        exchange=lease.exchange,
        mainnet=False,
        real_money=False,
        expected_runtime_sha=lease.expected_runtime_sha,
    )
    assert validate_runtime_lease(expired)["ok"] is False


def test_lease_session_id_prefix_and_full_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv("GITHUB_SHA", _TEST_SHA)
    lease = create_lease(founder_phrase=FOUNDER_PHRASE, expected_runtime_sha=_TEST_SHA)
    assert lease.session_id.startswith("NEXUS-DEMO-6H-V2-")
    loaded = RuntimeLease.from_dict(lease.to_runtime_payload())
    assert validate_runtime_lease(loaded)["ok"] is True
    assert validate_runtime_sha(expected=_TEST_SHA, deployed=_TEST_SHA)["ok"] is True


def test_certified_start_fails_without_signed_request(monkeypatch: pytest.MonkeyPatch) -> None:
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
    result = session.start(start_request=None)
    assert result.get("ok") is False


def test_signed_start_enables_session_start_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv("NEXUS_BOUNDED_SESSION_CONTROL_SECRET", _TEST_SECRET)
    monkeypatch.setenv("GITHUB_SHA", _TEST_SHA)
    lease = create_lease(founder_phrase=FOUNDER_PHRASE, expected_runtime_sha=_TEST_SHA)
    signed = sign_bounded_start_request(lease=lease.to_runtime_payload(), secret=_TEST_SECRET)
    assert verify_bounded_start_request(signed)["ok"] is True


def test_integration_qualification_offline_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv("NEXUS_BOUNDED_SESSION_CONTROL_SECRET", _TEST_SECRET)
    monkeypatch.setenv("GITHUB_SHA", _TEST_SHA)
    evidence = run_integration_qual(sqlite_path=tmp_path / "bounded_qual.db")
    assert evidence["BOUNDED_RUNTIME_CERTIFIED_SURFACE_WIRING_PASS"] is True
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0


def test_regression_lock_includes_bounded_runtime_wiring_test() -> None:
    assert "tests/test_bounded_runtime_certified_wiring.py" in HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES


def test_migration_0007_unchanged() -> None:
    assert MIGRATION_0007.is_file()
    text = MIGRATION_0007.read_text(encoding="utf-8")
    assert "p2_research_lessons" in text


def test_bounded_session_engine_subclass_preserves_base_type() -> None:
    assert issubclass(CertifiedBounded6HSession, BoundedAutonomousSessionEngine)


def test_session_mistake_memory_not_used_as_certified_guard() -> None:
    source = inspect.getsource(CertifiedBounded6HSession._try_entry)
    guard_block = source.split("for cand in candidates:")[1].split("persist_durable_intent")[0]
    assert "evaluate_certified_guard" in guard_block
    assert "self.memory.apply" not in guard_block.split("if guard_eval")[0]
