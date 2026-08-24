"""Bounded 6H runtime certified P1/P2 surface wiring — structural and integration proof."""
from __future__ import annotations

import inspect
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.nexus_bounded_runtime.bootstrap import install_certified_bounded_runtime
from backend.nexus_bounded_runtime.certified_session import CertifiedBounded6HSession, wiring_markers
from backend.nexus_bounded_runtime.runtime_lease import (
    RuntimeLease,
    lease_wiring_markers,
    load_runtime_lease,
    validate_runtime_lease,
)
from backend.nexus_demo_execution.bounded_autonomous_engine import BoundedAutonomousSessionEngine
from backend.nexus_demo_execution.session_mistake_memory import SessionMistakeMemory
from tools.ci.bounded_runtime_integration_qualification import run as run_integration_qual
from tools.ci.demo_bounded_session_lease import FOUNDER_PHRASE, create_lease
from tools.ci.p2_historical_p1_p2_regression_lock import HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES

ROOT = Path(__file__).resolve().parents[1]
FROZEN_ENGINE = ROOT / "backend/nexus_demo_execution/bounded_autonomous_engine.py"
MIGRATION_0007 = ROOT / "backend/nexus_persistence_pg/migrations/0007_p2_research_learning_store.sql"


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(key, "false")


def test_bootstrap_replaces_bounded_6h_session_class() -> None:
    install_certified_bounded_runtime()
    import backend.nexus_demo_execution.bounded_6h_session as mod

    assert mod.Bounded6HSession is CertifiedBounded6HSession


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
    assert "guard_eval.get(\"blocked\")" in source


def test_certified_session_requires_runtime_lease_at_start() -> None:
    source = inspect.getsource(CertifiedBounded6HSession.start)
    assert "load_runtime_lease" in source
    assert "validate_runtime_lease" in source
    assert "self.session_id = lease.session_id" in source


def test_wiring_markers_all_true() -> None:
    markers = wiring_markers()
    assert all(markers.values()), markers


def test_lease_wiring_markers_all_true() -> None:
    markers = lease_wiring_markers()
    assert all(markers.values()), markers


def test_runtime_rejects_missing_and_expired_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.delenv("BOUNDED_SESSION_LEASE_JSON", raising=False)
    monkeypatch.delenv("BOUNDED_SESSION_LEASE_PATH", raising=False)
    assert validate_runtime_lease(None)["ok"] is False

    lease = create_lease(founder_phrase=FOUNDER_PHRASE, expected_runtime_sha="abc1234")
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


def test_lease_session_id_prefix_matches_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    lease = create_lease(founder_phrase=FOUNDER_PHRASE, expected_runtime_sha="offline")
    assert lease.session_id.startswith("NEXUS-DEMO-6H-V2-")
    payload = json.dumps({"lease": lease.to_runtime_payload()})
    monkeypatch.setenv("BOUNDED_SESSION_LEASE_JSON", payload)
    monkeypatch.setenv("GITHUB_SHA", "offline")
    loaded = load_runtime_lease()
    assert loaded is not None
    assert validate_runtime_lease(loaded)["ok"] is True


def test_certified_start_fails_without_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.delenv("BOUNDED_SESSION_LEASE_JSON", raising=False)
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
    result = session.start()
    assert result.get("ok") is False
    assert result.get("reason") == "runtime_lease_missing"


def test_integration_qualification_offline_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _disarm(monkeypatch)
    evidence = run_integration_qual(sqlite_path=tmp_path / "bounded_qual.db")
    assert evidence["BOUNDED_RUNTIME_CERTIFIED_SURFACE_WIRING_PASS"] is True
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0
    assert evidence["REAL_EXCHANGE_WRITE_CALLS"] == 0


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
