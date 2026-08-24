"""Founder-approved bounded 6H Bybit Demo autonomous session — offline contract."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL
from backend.nexus_demo_execution.session_limits import (
    FIXED_LEVERAGE,
    MARGIN_PER_TRADE_CAP,
    MAX_CONCURRENT_POSITIONS,
    SESSION_DURATION_SEC,
)
from tools.ci.demo_bounded_session_lease import (
    FOUNDER_PHRASE,
    BoundedSessionLease,
    SESSION_DURATION_HOURS,
    create_lease,
    expiry_blocks_new_entry,
    is_expired,
    load_lease,
    save_lease,
    writes_allowed,
)
from tools.ci.demo_bounded_session_orchestrator import (
    activate_session,
    prepare_session,
    run_qualification,
    stop_session,
)
from tools.ci.demo_bounded_session_preflight import run_preflight
from tools.ci.p2_failure_mode_e2e_qualification import run as run_failure_mode
from tools.ci.p2_migration_service_identity import LEARNING_VALIDATION_SERVICE_NAME

ROOT = Path(__file__).resolve().parents[1]
START_WORKFLOW = ROOT / ".github/workflows/founder_approved_bybit_demo_bounded_autonomous_session.yml"
STOP_WORKFLOW = ROOT / ".github/workflows/founder_approved_bybit_demo_bounded_session_stop.yml"
MIGRATION_0007 = ROOT / "backend/nexus_persistence_pg/migrations/0007_p2_research_learning_store.sql"


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(key, "false")


def test_session_duration_is_six_hours() -> None:
    assert SESSION_DURATION_HOURS == 6
    assert SESSION_DURATION_SEC == 6 * 60 * 60


def test_lease_requires_exact_founder_phrase() -> None:
    with pytest.raises(ValueError, match="founder_phrase_invalid"):
        create_lease(founder_phrase="WRONG_PHRASE")


def test_lease_create_and_persist_roundtrip(tmp_path: Path) -> None:
    lease = create_lease(founder_phrase=FOUNDER_PHRASE)
    path = tmp_path / "lease.json"
    save_lease(lease, path)
    loaded = load_lease(path)
    assert loaded is not None
    assert loaded.session_id == lease.session_id
    assert loaded.mainnet is False
    assert loaded.real_money is False
    assert loaded.exchange == "BYBIT_DEMO"


def test_expired_lease_blocks_writes() -> None:
    lease = create_lease(founder_phrase=FOUNDER_PHRASE)
    expired = BoundedSessionLease(
        session_id=lease.session_id,
        authorized_at=lease.authorized_at,
        expires_at="2000-01-01T00:00:00Z",
        exchange=lease.exchange,
        mainnet=False,
        real_money=False,
        founder_phrase_hash=lease.founder_phrase_hash,
    )
    assert expiry_blocks_new_entry(expired) is True
    assert writes_allowed(expired) is False


def test_unresolved_intent_blocks_writes() -> None:
    lease = create_lease(founder_phrase=FOUNDER_PHRASE)
    assert writes_allowed(lease, unresolved_intent_count=1) is False


def test_offline_preflight_passes_with_founder_phrase(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    report = run_preflight(
        founder_phrase=FOUNDER_PHRASE,
        expected_github_sha="offline",
        offline=True,
    )
    assert report["preflight_pass"] is True
    assert report["checks"]["BYBIT_DEMO_ONLY"] is True
    assert report["checks"]["MIGRATION_0007_PRESENT"] is True
    assert report["checks"]["REPEAT_MISTAKE_GUARD_HEALTHY"] is True
    assert report["checks"]["RISK_ENGINE_FINAL_AUTHORITY"] is True


def test_preflight_holds_on_bad_founder_phrase(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    report = run_preflight(founder_phrase="BAD", offline=True)
    assert report["preflight_pass"] is False
    assert report["hold_reason"] is not None


def test_prepare_session_offline_not_hold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _disarm(monkeypatch)
    evidence = prepare_session(
        founder_phrase=FOUNDER_PHRASE,
        offline=True,
        expected_github_sha="offline",
        lease_path=tmp_path / "lease.json",
    )
    assert evidence["HOLD"] is False
    assert evidence["session_id"]
    assert evidence["SESSION_LEASE_IMPLEMENTED"] is True


def test_activate_and_stop_dry_run_do_not_write() -> None:
    lease = create_lease(founder_phrase=FOUNDER_PHRASE)
    activate = activate_session(lease=lease, dry_run=True)
    stop = stop_session(dry_run=True)
    assert activate["dry_run"] is True
    assert stop["dry_run"] is True


def test_qualification_markers_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    evidence = run_qualification(offline=True)
    assert evidence["BOUNDED_DEMO_SESSION_READY"] is True
    assert evidence["SESSION_LEASE_IMPLEMENTED"] is True
    assert evidence["SESSION_EXPIRY_BLOCKS_NEW_ENTRY"] is True
    assert evidence["ONE_ACTIVE_POSITION_LIMIT"] is True
    assert evidence["FOUNDER_STOP_CONTROL_IMPLEMENTED"] is True
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0


def test_one_active_position_limit() -> None:
    assert MAX_CONCURRENT_POSITIONS == 1


def test_risk_engine_constants_unchanged() -> None:
    assert FIXED_LEVERAGE == 25
    assert float(MARGIN_PER_TRADE_CAP) == 20.0


def test_demo_api_is_demo_only() -> None:
    assert "api-demo.bybit.com" in DEMO_REST_BASE_URL


def test_failure_mode_e2e_still_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    evidence = run_failure_mode()
    assert evidence["FAILURE_MODE_E2E_PASS"] is True


def test_start_workflow_contract() -> None:
    source = START_WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "START_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION" in source
    assert "nexus-bybit-demo-learning-validation" in source
    assert "nexus-p2-migration-control" not in source
    assert "p2_historical_p1_p2_regression_lock" in source
    assert "demo_bounded_session" in source
    for flag in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        assert flag in source


def test_stop_workflow_contract() -> None:
    source = STOP_WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "STOP_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION" in source
    assert "bounded-6h/stop" in source or "demo_bounded_session_orchestrator" in source


def test_runtime_service_not_migration_control() -> None:
    assert LEARNING_VALIDATION_SERVICE_NAME == "nexus-bybit-demo-learning-validation"


def test_migration_0007_unchanged() -> None:
    sql = MIGRATION_0007.read_text(encoding="utf-8")
    assert "p2_research_lessons" in sql
    assert "DROP TABLE" not in sql.upper()


def test_lease_expires_after_six_hours() -> None:
    start = datetime(2026, 8, 24, 0, 0, 0, tzinfo=timezone.utc)
    lease = create_lease(founder_phrase=FOUNDER_PHRASE, now=start)
    assert not is_expired(lease, now=start + timedelta(hours=5, minutes=59))
    assert is_expired(lease, now=start + timedelta(hours=6, seconds=1))
