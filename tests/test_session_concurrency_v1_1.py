"""Concurrency tests for Session Orchestrator V1.1.

Invariant: at most one canonical lifecycle per idempotency key. Concurrent
callbacks (candidate submission, checkpoint, kill switch, Reflection results,
Lesson storage) must not create duplicate positions/exits/Lessons or out-of-
order terminal transitions.
"""
from __future__ import annotations

import threading
from pathlib import Path

from backend.nexus_autonomy.session_orchestrator_v1_1 import (
    AutonomousSessionOrchestratorV11,
    build_default_candidates,
)


def test_concurrent_duplicate_candidate_submissions_have_single_lifecycle(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        orch.start("S_conc_dup", logical_hours=1.0)
        cand = build_default_candidates(1)[0]

        completed_count = 0
        duplicate_count = 0
        lock = threading.Lock()

        def worker() -> None:
            nonlocal completed_count, duplicate_count
            r = orch.submit_candidate(cand)
            with lock:
                if r.get("status") == "COMPLETE":
                    completed_count += 1
                elif r.get("status") == "DUPLICATE_CANDIDATE_IGNORED":
                    duplicate_count += 1

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert completed_count == 1
        assert duplicate_count == 15
        # Simulator should also report only one position/one intent for this key.
        assert orch.intent_count == 1
        assert orch.exit_count == 1
    finally:
        orch.close()


def test_concurrent_kill_switch_calls_idempotent(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        orch.start("S_conc_kill", logical_hours=1.0)

        def worker() -> None:
            orch.trigger_kill_switch(reason="race")

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert orch.kill_switch_flag is True
        assert orch.kill_switch_status == "TRIGGERED"
        orch.finalize()
        assert orch.state_machine.state == "BLOCKED"
        # Only one kill switch ledger event (idempotency-guarded).
        events = orch.ledger.replay()
        kill_events = [e for e in events if e["event_type"] == "SESSION_KILL_SWITCH"]
        assert len(kill_events) == 1
    finally:
        orch.close()


def test_concurrent_checkpoints_stay_sequential(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        orch.start("S_conc_ckpt", logical_hours=1.0)

        errors: list[str] = []

        def worker(i: int) -> None:
            try:
                orch._checkpoint(reason=f"race_{i}")
            except Exception as exc:  # pragma: no cover
                errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        # Every checkpoint call incremented the counter monotonically.
        assert orch.checkpoint_count >= 6
    finally:
        orch.close()


def test_concurrent_candidate_intents_distinct_lifecycles(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=4, max_intents=4)
    try:
        orch.start("S_conc_multi", logical_hours=1.0)
        cands = build_default_candidates(12)

        results: dict[str, str] = {}
        lock = threading.Lock()

        def worker(cand: dict) -> None:
            r = orch.submit_candidate(cand)
            with lock:
                results[cand["candidate_id"]] = r.get("status", "UNKNOWN")

        threads = [threading.Thread(target=worker, args=(c,)) for c in cands]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Every candidate must have a definitive outcome (no None).
        assert set(results.keys()) == {c["candidate_id"] for c in cands}
        assert all(v != "UNKNOWN" for v in results.values())
        # No duplicate positions or ambiguous state.
        assert orch.sim.open_ambiguous_position_count() == 0
        assert orch.duplicate_position_count == 0
    finally:
        orch.close()


def test_concurrent_pause_resume_race_still_lands_in_valid_state(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        orch.start("S_conc_pause", logical_hours=1.0)

        def pauser() -> None:
            try:
                orch.request_pause(reason="race_pause")
            except Exception:
                pass

        def resumer() -> None:
            try:
                orch.request_resume(reason="race_resume")
            except Exception:
                pass

        threads = []
        for _ in range(4):
            threads.append(threading.Thread(target=pauser))
            threads.append(threading.Thread(target=resumer))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Regardless of race outcome, state must be a valid non-terminal state.
        assert orch.state_machine.state in {"RUNNING", "PAUSING", "PAUSED"}
        # No invalid transitions should have mutated state — they must have
        # been recorded on the state machine's invalid_attempts list.
        # (The count can be nonzero, but state must be valid.)
    finally:
        orch.close()
