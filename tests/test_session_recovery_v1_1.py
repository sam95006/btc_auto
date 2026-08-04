"""Recovery tests for Session Orchestrator V1.1.

Covers: restart-from-checkpoint, missing snapshot fail-closed, snapshot
corruption detection, ambiguous state routing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_autonomy.session_orchestrator_v1_1 import (
    AutonomousSessionOrchestratorV11,
    build_default_candidates,
)
from backend.nexus_recovery.crash_recovery import (
    SessionCrashRecovery,
    recover_from_checkpoint,
)
from backend.nexus_recovery.invariants import check_recovery_invariants


def test_recovery_invariants_pass_when_all_zero() -> None:
    inv = check_recovery_invariants({})
    assert inv.passed is True
    assert inv.violations == []


def test_recovery_invariants_fail_on_any_nonzero() -> None:
    inv = check_recovery_invariants({"unclosed_intent_count": 2})
    assert inv.passed is False
    assert "unclosed_intent_count=2" in inv.violations


def test_recover_from_checkpoint_after_clean_run(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        cands = build_default_candidates(20)
        result = orch.run_accelerated_session(
            session_id="S_recover_clean",
            logical_hours=24,
            candidates=cands,
            injections=[],
            checkpoint_every=5,
        )
        assert result.final_state == "COMPLETED"
    finally:
        orch.close()

    outcome = recover_from_checkpoint(tmp_path, "S_recover_clean")
    assert outcome.status in {"RECOVERED"}
    assert outcome.invariants is not None
    assert outcome.invariants.passed is True


def test_recover_from_missing_lkg_blocks_ambiguous(tmp_path: Path) -> None:
    # No session has ever been created — no LKG file exists.
    outcome = recover_from_checkpoint(tmp_path, "S_missing")
    assert outcome.status == "BLOCKED_AMBIGUOUS"
    assert outcome.reason == "lkg_restore_blocked"


def test_recover_after_snapshot_corruption_blocks(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        orch.start("S_corrupt", logical_hours=1.0)
        orch.close()
    finally:
        pass
    lkg_path = tmp_path / "durability" / "last_known_good.json"
    assert lkg_path.exists()
    pointer = json.loads(lkg_path.read_text(encoding="utf-8"))
    pointer["snapshot_checksum"] = "0" * 64
    lkg_path.write_text(json.dumps(pointer) + "\n", encoding="utf-8")

    outcome = recover_from_checkpoint(tmp_path, "S_corrupt")
    assert outcome.status == "BLOCKED_AMBIGUOUS"
    assert outcome.reason == "snapshot_corruption"


def test_partial_fill_crash_recovery_routes_via_recovery(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        orch.start("S_partial_crash", logical_hours=1.0)
        # Simulate a partial fill crash + recovery path.
        rec = orch.simulate_partial_fill_crash_recovery()
        # No positions in flight so recovery must return RECOVERED.
        assert rec.status in {"RECOVERED"}
        assert orch.restart_count == 1
    finally:
        orch.close()


def test_process_termination_then_reopen(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        cands = build_default_candidates(40)
        result = orch.run_accelerated_session(
            session_id="S_proc_term_reopen",
            logical_hours=24,
            candidates=cands,
            injections=["process_termination"],
            checkpoint_every=10,
            restart_after_index=15,
        )
        assert result.final_state in {"COMPLETED", "BLOCKED"}
        assert result.restart_count >= 1
        assert result.recovery_count >= 1
        assert result.invariants_status == "PASS"
        assert result.exchange_write_attempt_count == 0
    finally:
        orch.close()


def test_recovery_never_causes_exchange_write(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        cands = build_default_candidates(30)
        orch.run_accelerated_session(
            session_id="S_recov_noexch",
            logical_hours=24,
            candidates=cands,
            injections=["process_termination", "snapshot_corruption", "missing_latest_snapshot"],
            checkpoint_every=8,
            restart_after_index=12,
        )
        assert orch.guard.exchange_write_attempt_count == 0
    finally:
        orch.close()
