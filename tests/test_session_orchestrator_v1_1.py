"""Tests for NEXUS Autonomous Session Orchestrator V1.1."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_autonomy.session_chaos_recovery_v1_1 import (
    FROZEN_SEED,
    PASS_STATUS,
    candidate_count_for_hours,
    run_one_chaos_session,
    run_session_chaos_campaign,
)
from backend.nexus_autonomy.session_orchestrator_v1_1 import (
    INJECTION_CATALOG,
    AutonomousSessionOrchestratorV11,
    build_default_candidates,
)
from backend.nexus_autonomy.session_state_machine import SessionStateMachine, InvalidTransitionError
from backend.nexus_recovery.invariants import REQUIRED_ZERO_INVARIANTS, check_recovery_invariants


INVARIANT_KEYS = REQUIRED_ZERO_INVARIANTS


def _assert_invariants(counts: dict) -> None:
    for k in INVARIANT_KEYS:
        assert int(counts.get(k, 0)) == 0, f"{k}={counts.get(k)}"


def test_state_machine_fail_closed():
    sm = SessionStateMachine("s1")
    sm.transition("INITIALIZING", reason="t", idempotency_key="a")
    sm.transition("RUNNING", reason="t", idempotency_key="b")
    try:
        sm.transition("COMPLETED", reason="illegal", idempotency_key="c")
        assert False, "expected InvalidTransitionError"
    except InvalidTransitionError:
        pass
    assert sm.state == "RUNNING"


def test_session_24h_invariants(tmp_path: Path):
    report = run_one_chaos_session(
        tmp_path / "s24",
        session_id="T24",
        logical_hours=24.0,
        seed=FROZEN_SEED,
    )
    _assert_invariants(report["invariants_counts"])
    assert report["session_pass"] is True
    assert report["metrics"]["checkpoint_count"] >= 1
    assert report["metrics"]["events_processed"] >= 1
    assert report["final_state"] in {"COMPLETED", "BLOCKED"}


def test_session_72h_chaos_recovery(tmp_path: Path):
    report = run_one_chaos_session(
        tmp_path / "s72",
        session_id="T72",
        logical_hours=72.0,
        seed=FROZEN_SEED + 72,
    )
    _assert_invariants(report["invariants_counts"])
    assert report["session_pass"] is True
    assert report["restart_count"] >= 0
    assert report["recovery_count"] >= 0


def test_session_168h_metrics(tmp_path: Path):
    report = run_one_chaos_session(
        tmp_path / "s168",
        session_id="T168",
        logical_hours=168.0,
        seed=FROZEN_SEED + 168,
    )
    _assert_invariants(report["invariants_counts"])
    assert report["session_pass"] is True
    assert report["logical_duration_hours"] == 168.0
    for key in (
        "events_processed",
        "checkpoint_count",
        "restart_count",
        "recovery_duration_ms",
        "memory_growth_bytes",
        "cpu_time_ms",
        "ledger_size_bytes",
        "snapshot_size_bytes",
    ):
        assert key in report["metrics"]


def test_campaign_24_72_168_pass(tmp_path: Path):
    package = run_session_chaos_campaign(tmp_path / "campaign", seed=FROZEN_SEED)
    assert package["Session_Chaos_status"] == PASS_STATUS, package
    _assert_invariants(package["invariants"])
    assert set(package["logical_sessions_hours"]) == {24.0, 72.0, 168.0}
    assert package["exchange_write_attempt_count"] == 0
    assert len(package["chaos_catalog"]) == len(INJECTION_CATALOG)


def test_invariants_helper_rejects_nonzero():
    r = check_recovery_invariants({"open_ambiguous_position_count": 1})
    assert r.passed is False
    assert "open_ambiguous_position_count=1" in r.violations


def test_candidate_count_covers_catalog():
    assert candidate_count_for_hours(24) >= 60
    assert len(build_default_candidates(10)) == 10


def test_orchestrator_no_exchange_write(tmp_path: Path):
    orch = AutonomousSessionOrchestratorV11(tmp_path)
    try:
        result = orch.run_accelerated_session(
            session_id="NOW",
            logical_hours=1.0,
            candidates=build_default_candidates(8),
            injections=["provider_timeout", "stale_market_data", "duplicate_order_intent"],
            checkpoint_every=3,
            restart_after_index=2,
        )
    finally:
        orch.close()
    assert result.exchange_write_attempt_count == 0
    _assert_invariants(result.invariants_counts)
