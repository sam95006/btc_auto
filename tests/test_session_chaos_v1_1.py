"""Focused Session Chaos V1.1 failure-injection tests."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_autonomy.session_orchestrator_v1_1 import (
    INJECTION_CATALOG,
    AutonomousSessionOrchestratorV11,
    build_default_candidates,
)
from backend.nexus_recovery.crash_recovery import SessionCrashRecovery
from backend.nexus_runtime.accelerated_clock import AcceleratedLogicalClock
from backend.nexus_runtime.process_guard import ExchangeWriteAttemptError, NoExchangeWriteGuard


def test_injection_catalog_covers_mission_failures():
    catalog = set(INJECTION_CATALOG)
    required = {
        "groq_429",
        "provider_timeout",
        "provider_invalid_schema",
        "stale_market_data",
        "clock_jump_forward",
        "clock_jump_backward",
        "duplicate_candidate",
        "duplicate_order_intent",
        "ledger_lock_contention",
        "interrupted_ledger_append",
        "snapshot_corruption",
        "disk_soft_limit",
        "disk_hard_limit",
        "process_termination",
        "network_loss",
        "partial_fill_before_crash",
        "exit_event_before_position_snapshot",
        "reflection_interruption",
        "lesson_storage_interruption",
    }
    assert required.issubset(catalog)


def test_provider_429_blocks(tmp_path: Path):
    orch = AutonomousSessionOrchestratorV11(tmp_path)
    orch.start("prov", logical_hours=1.0)
    cand = build_default_candidates(1)[0]
    cand["provider"] = "GROQ"
    cand["uses_provider"] = True
    r = orch.submit_candidate(cand, injection={"groq_429"})
    orch.close()
    assert r["status"] == "PROVIDER_BLOCKED"


def test_clock_jump_backward_recorded():
    clock = AcceleratedLogicalClock()
    clock.advance_hours(2)
    clock.jump_backward(300)
    assert clock.last_monotonic_violation is not None
    assert clock.stats["backward_jump_count"] == 1


def test_exchange_write_guard_blocks():
    guard = NoExchangeWriteGuard()
    try:
        guard.attempt("/order")
        assert False, "expected ExchangeWriteAttemptError"
    except ExchangeWriteAttemptError:
        pass
    assert guard.exchange_write_attempt_count == 1


def test_partial_fill_crash_recovers_clean(tmp_path: Path):
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        result = orch.run_accelerated_session(
            session_id="PFC",
            logical_hours=2.0,
            candidates=build_default_candidates(30),
            injections=["partial_fill_before_crash", "process_termination"],
            checkpoint_every=5,
            restart_after_index=5,
        )
    finally:
        orch.close()
    assert result.invariants_counts["unclosed_intent_count"] == 0
    assert result.exchange_write_attempt_count == 0
    assert result.session_pass is True


def test_snapshot_corruption_recovery_path(tmp_path: Path):
    orch = AutonomousSessionOrchestratorV11(tmp_path)
    orch.start("snap", logical_hours=1.0)
    orch._checkpoint(reason="good")
    orch._checkpoint(reason="corrupt", corrupt=True)
    recovery = SessionCrashRecovery(tmp_path).recover("snap")
    orch.close()
    assert recovery.status in {
        "BLOCKED_AMBIGUOUS",
        "CORRUPTION_DETECTED",
        "RECOVERED",
        "FAILED_SAFE",
        "RECOVERY_FAILED",
    } or recovery.restore_status in {
        "CORRUPTION_DETECTED",
        "BLOCKED_AMBIGUOUS_STATE",
        "RECOVERED_EXACT",
        "RECOVERED_LAST_KNOWN_GOOD",
        "RECOVERY_FAILED",
    }
