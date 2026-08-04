"""Focused tests for the Autonomous Session Orchestrator V1.1.

Covers: session lifecycle, valid/invalid transitions, invariants, kill
switch behavior, and clean 24h session end-to-end.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.nexus_autonomy.session_orchestrator_v1_1 import (
    AutonomousSessionOrchestratorV11,
    LONG_SESSION_INJECTIONS,
    build_default_candidates,
)


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path


def _make(root: Path, **kwargs) -> AutonomousSessionOrchestratorV11:
    return AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2, **kwargs)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_start_transitions_to_running(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        orch.start("S1", logical_hours=1.0)
        assert orch.state_machine is not None
        assert orch.state_machine.state == "RUNNING"
        # start also emits SESSION_START ledger event and initial checkpoint.
        assert orch.checkpoint_count >= 1
    finally:
        orch.close()


def test_pause_and_resume_round_trip(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        orch.start("S2", logical_hours=1.0)
        orch.request_pause(reason="unit_test")
        assert orch.state_machine.state == "PAUSED"
        orch.request_resume(reason="unit_test")
        assert orch.state_machine.state == "RUNNING"
    finally:
        orch.close()


def test_finalize_transitions_to_completed(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        orch.start("S3", logical_hours=1.0)
        orch.finalize(reason="unit_test")
        assert orch.state_machine.state == "COMPLETED"
    finally:
        orch.close()


def test_kill_switch_marks_terminal_blocked(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        orch.start("S4", logical_hours=1.0)
        orch.trigger_kill_switch(reason="unit_test")
        assert orch.kill_switch_flag is True
        assert orch.kill_switch_status == "TRIGGERED"
        assert orch.guard.exchange_write_attempt_count == 0
        orch.finalize(reason="post_kill")
        # kill switch drives finalize to BLOCKED, not COMPLETED.
        assert orch.state_machine.state == "BLOCKED"
    finally:
        orch.close()


# ---------------------------------------------------------------------------
# Invariants + long session smoke
# ---------------------------------------------------------------------------

def test_24h_long_session_completes_clean(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        cands = build_default_candidates(24)
        result = orch.run_accelerated_session(
            session_id="S24",
            logical_hours=24,
            candidates=cands,
            injections=list(LONG_SESSION_INJECTIONS),
            checkpoint_every=8,
        )
        d = result.to_dict()
        assert d["final_state"] == "COMPLETED"
        assert d["session_pass"] is True
        assert d["invariants_status"] == "PASS"
        assert d["exchange_write_attempt_count"] == 0
        for k in (
            "open_ambiguous_position_count",
            "orphan_lifecycle_count",
            "duplicate_position_count",
            "unclosed_intent_count",
            "untracked_fill_count",
            "risk_limit_bypass_count",
            "exchange_write_attempt_count",
        ):
            assert d["invariants_counts"][k] == 0
        # candidate_count reflects distinct submissions; duplicate_candidate
        # injection re-uses earlier ids so a few will be de-duplicated.
        assert 20 <= d["candidate_count"] <= 24
        assert d["invalid_transition_attempts"] == 0
    finally:
        orch.close()


def test_reflection_and_lesson_queues_advance(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        cands = build_default_candidates(24)
        result = orch.run_accelerated_session(
            session_id="S_reflection",
            logical_hours=24,
            candidates=cands,
            injections=[],  # no injections — every completed trade queues both.
            checkpoint_every=8,
        )
        # With 24 clean candidates and max_positions=2, most complete.
        assert result.reflection_queue_len > 0
        assert result.lesson_queue_len > 0
        assert result.reflection_queue_len == result.lesson_queue_len
    finally:
        orch.close()


def test_no_exchange_write_attempts(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        cands = build_default_candidates(30)
        result = orch.run_accelerated_session(
            session_id="S_noexch",
            logical_hours=24,
            candidates=cands,
            injections=list(LONG_SESSION_INJECTIONS),
            checkpoint_every=10,
        )
        assert result.exchange_write_attempt_count == 0
        assert orch.guard.exchange_write_attempt_count == 0
    finally:
        orch.close()


def test_duplicate_candidate_is_ignored(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        orch.start("Sdup", logical_hours=1.0)
        cand = build_default_candidates(1)[0]
        first = orch.submit_candidate(cand)
        second = orch.submit_candidate(cand)
        assert first["status"] == "COMPLETE"
        assert second["status"] == "DUPLICATE_CANDIDATE_IGNORED"
    finally:
        orch.close()


def test_risk_override_rejected(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        orch.start("Srisk", logical_hours=1.0)
        cand = build_default_candidates(1)[0]
        cand["risk_override"] = True
        cand["candidate_id"] = "risky"
        cand["idempotency_key"] = "risky_key"
        result = orch.submit_candidate(cand)
        assert result["status"] == "RISK_OVERRIDE_REJECTED"
        # No intent counted.
        assert orch.intent_count == 0
    finally:
        orch.close()


def test_start_bound_to_single_session(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        orch.start("A", logical_hours=1.0)
        with pytest.raises(RuntimeError):
            orch.start("B", logical_hours=1.0)
    finally:
        orch.close()


def test_state_history_contains_lifecycle_events(tmp_root: Path) -> None:
    orch = _make(tmp_root)
    try:
        orch.start("Shist", logical_hours=1.0)
        orch.request_pause(reason="rp")
        orch.request_resume(reason="rs")
        orch.finalize(reason="ok")
        assert orch.state_machine.state == "COMPLETED"
        seq = [h["next_state"] for h in orch.state_machine.history()]
        assert "INITIALIZING" in seq
        assert "RUNNING" in seq
        assert "PAUSING" in seq
        assert "PAUSED" in seq
        assert "FINALIZING" in seq
        assert "COMPLETED" in seq
    finally:
        orch.close()
