"""Focused tests for the canonical Session State Machine V1.1."""
from __future__ import annotations

import threading

import pytest

from backend.nexus_autonomy.session_state_machine import (
    CANONICAL_STATES,
    InvalidTransitionError,
    SessionStateMachine,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    is_valid_transition,
    transition_table,
)


def test_canonical_states_enumerated() -> None:
    expected = {
        "CREATED", "INITIALIZING", "RUNNING", "PAUSING", "PAUSED",
        "RECOVERING", "FINALIZING", "COMPLETED", "BLOCKED", "FAILED_SAFE",
    }
    assert set(CANONICAL_STATES) == expected
    assert TERMINAL_STATES == frozenset({"COMPLETED", "BLOCKED", "FAILED_SAFE"})


def test_transition_table_has_no_terminal_outgoing_edges() -> None:
    table = transition_table()
    for terminal in TERMINAL_STATES:
        assert table[terminal] == []


def test_happy_path_transitions() -> None:
    sm = SessionStateMachine("S1")
    sm.transition("INITIALIZING", reason="init", idempotency_key="a")
    sm.transition("RUNNING", reason="run", idempotency_key="b")
    sm.transition("FINALIZING", reason="deadline", idempotency_key="c")
    sm.transition("COMPLETED", reason="done", idempotency_key="d")
    assert sm.state == "COMPLETED"
    assert sm.is_terminal
    assert sm.invalid_attempt_count() == 0


def test_invalid_transition_fails_closed_and_logs() -> None:
    sm = SessionStateMachine("S2")
    sm.transition("INITIALIZING", reason="init", idempotency_key="a")
    with pytest.raises(InvalidTransitionError):
        # RUNNING is not reachable from INITIALIZING via "PAUSED" — need RUNNING first.
        sm.transition("PAUSED", reason="pause_from_init", idempotency_key="bad")
    # State did not mutate.
    assert sm.state == "INITIALIZING"
    # Attempt was recorded.
    attempts = sm.invalid_attempts()
    assert len(attempts) == 1
    assert attempts[0]["reason"] == "invalid_transition"


def test_unknown_state_rejected() -> None:
    sm = SessionStateMachine("S3")
    with pytest.raises(InvalidTransitionError):
        sm.transition("MADE_UP_STATE", reason="x", idempotency_key="i1")


def test_idempotent_transition_returns_same_record() -> None:
    sm = SessionStateMachine("S4")
    r1 = sm.transition("INITIALIZING", reason="init", idempotency_key="k1")
    r2 = sm.transition("INITIALIZING", reason="init", idempotency_key="k1")
    assert r1.event_id == r2.event_id
    assert len(sm.history()) == 1


def test_idempotency_key_conflict_rejected() -> None:
    sm = SessionStateMachine("S5")
    sm.transition("INITIALIZING", reason="init", idempotency_key="k1")
    with pytest.raises(InvalidTransitionError):
        # Same key, DIFFERENT target — must fail closed.
        sm.transition("BLOCKED", reason="conflict", idempotency_key="k1")


def test_terminal_state_has_no_outgoing_transitions() -> None:
    sm = SessionStateMachine("S6")
    for step in ("INITIALIZING", "RUNNING", "FINALIZING", "COMPLETED"):
        sm.transition(step, reason=step.lower(), idempotency_key=step)
    assert sm.is_terminal
    with pytest.raises(InvalidTransitionError):
        sm.transition("RUNNING", reason="try_reopen", idempotency_key="rerun")


def test_force_failed_safe_from_any_non_terminal_state() -> None:
    for start_state in ("CREATED", "INITIALIZING", "RUNNING", "PAUSING", "PAUSED", "RECOVERING", "FINALIZING"):
        sm = SessionStateMachine(f"S7_{start_state}")
        # Drive to the required starting state via valid path.
        path = {
            "CREATED": [],
            "INITIALIZING": ["INITIALIZING"],
            "RUNNING": ["INITIALIZING", "RUNNING"],
            "PAUSING": ["INITIALIZING", "RUNNING", "PAUSING"],
            "PAUSED": ["INITIALIZING", "RUNNING", "PAUSING", "PAUSED"],
            "RECOVERING": ["INITIALIZING", "RUNNING", "RECOVERING"],
            "FINALIZING": ["INITIALIZING", "RUNNING", "FINALIZING"],
        }[start_state]
        for i, s in enumerate(path):
            sm.transition(s, reason=f"step{i}", idempotency_key=f"k{i}")
        record = sm.force_failed_safe(reason="emergency", idempotency_key=f"ff_{start_state}")
        assert sm.state == "FAILED_SAFE"
        assert record.next_state == "FAILED_SAFE"


def test_force_failed_safe_preserves_existing_terminal_state() -> None:
    sm = SessionStateMachine("S8")
    for step in ("INITIALIZING", "RUNNING", "FINALIZING", "COMPLETED"):
        sm.transition(step, reason=step, idempotency_key=step)
    sm.force_failed_safe(reason="try_override", idempotency_key="override")
    # Terminal state preserved — cannot mutate to FAILED_SAFE after COMPLETED.
    assert sm.state == "COMPLETED"
    assert any(a["reason"] == "force_failed_safe_after_terminal" for a in sm.invalid_attempts())


def test_pause_and_recover_cycle() -> None:
    sm = SessionStateMachine("S9")
    sm.transition("INITIALIZING", reason="i", idempotency_key="i")
    sm.transition("RUNNING", reason="r", idempotency_key="r")
    sm.transition("PAUSING", reason="p1", idempotency_key="p1")
    sm.transition("PAUSED", reason="p2", idempotency_key="p2")
    sm.transition("RUNNING", reason="resume", idempotency_key="resume")
    sm.transition("RECOVERING", reason="rec", idempotency_key="rec")
    sm.transition("RUNNING", reason="rec_ok", idempotency_key="rec_ok")
    sm.transition("FINALIZING", reason="deadline", idempotency_key="fin")
    sm.transition("COMPLETED", reason="done", idempotency_key="done")
    assert sm.state == "COMPLETED"


def test_serialize_and_restore_roundtrip() -> None:
    sm = SessionStateMachine("S10")
    sm.transition("INITIALIZING", reason="a", idempotency_key="a")
    sm.transition("RUNNING", reason="b", idempotency_key="b")
    blob = sm.serialize()
    sm2 = SessionStateMachine.restore(blob)
    assert sm2.state == sm.state
    assert [h["event_id"] for h in sm2.history()] == [h["event_id"] for h in sm.history()]


def test_transition_metadata_sanitizes_secret_like_fields() -> None:
    sm = SessionStateMachine("S11")
    sm.transition("INITIALIZING", reason="init", idempotency_key="i", metadata={"note": "x"})
    r = sm.transition(
        "RUNNING",
        reason="run",
        idempotency_key="r",
        metadata={"api_key": "shouldnotpersist", "safe": "ok", "password": "nope"},
    )
    assert "api_key" not in r.metadata
    assert "password" not in r.metadata
    assert r.metadata.get("safe") == "ok"


def test_concurrent_transitions_serialize_correctly() -> None:
    sm = SessionStateMachine("S12")
    sm.transition("INITIALIZING", reason="init", idempotency_key="init")
    sm.transition("RUNNING", reason="run", idempotency_key="run")

    results: list[str] = []
    errors: list[str] = []

    def worker(idx: int) -> None:
        try:
            sm.transition(
                "PAUSING",
                reason=f"race{idx}",
                idempotency_key=f"race{idx}",
            )
            results.append("pause_ok")
        except InvalidTransitionError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Exactly one PAUSING transition should have taken effect; the others
    # must have hit invalid_transition (already in PAUSING) and failed closed.
    assert sm.state in {"PAUSING"}
    assert len(results) == 1
    assert len(errors) == 7


def test_all_transitions_produce_event_id_and_ledger_seq() -> None:
    sm = SessionStateMachine("S13")
    r = sm.transition(
        "INITIALIZING",
        reason="init",
        idempotency_key="i",
        checkpoint_id="ckpt_1",
        ledger_sequence=42,
    )
    assert r.event_id
    assert r.timestamp
    assert r.checkpoint_id == "ckpt_1"
    assert r.ledger_sequence == 42
    assert r.previous_state == "CREATED"
    assert r.next_state == "INITIALIZING"


@pytest.mark.parametrize("prev,nxt,ok", [
    ("CREATED", "INITIALIZING", True),
    ("CREATED", "RUNNING", False),
    ("RUNNING", "PAUSING", True),
    ("RUNNING", "COMPLETED", False),  # must go via FINALIZING
    ("PAUSED", "RUNNING", True),
    ("COMPLETED", "RUNNING", False),
    ("BLOCKED", "RUNNING", False),
    ("FAILED_SAFE", "RUNNING", False),
    ("FINALIZING", "COMPLETED", True),
])
def test_transition_table_matrix(prev: str, nxt: str, ok: bool) -> None:
    assert is_valid_transition(prev, nxt) is ok
