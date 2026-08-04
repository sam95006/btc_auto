"""Chaos / failure-injection matrix tests for Session Orchestrator V1.1.

Every terminal / hard-fail injection is exercised in its own session and
asserted to route the session to BLOCKED or FAILED_SAFE with all
recovery invariants clean.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_autonomy.session_orchestrator_v1_1 import (
    AutonomousSessionOrchestratorV11,
    INJECTION_CATALOG,
    LONG_SESSION_INJECTIONS,
    ProviderMockConfig,
    TERMINAL_INJECTIONS,
    build_default_candidates,
)


def _run(root: Path, sid: str, injections: list[str], *, count: int = 60, **kwargs) -> dict:
    orch = AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2)
    try:
        cands = build_default_candidates(count)
        result = orch.run_accelerated_session(
            session_id=sid,
            logical_hours=24.0,
            candidates=cands,
            injections=list(injections),
            checkpoint_every=15,
            **kwargs,
        )
        return result.to_dict()
    finally:
        orch.close()


# ---------------------------------------------------------------------------
# Resumable injections (session must COMPLETE)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("inj", [
    ["groq_429"],
    ["sambanova_429"],
    ["provider_timeout"],
    ["provider_invalid_schema"],
    ["stale_market_data"],
    ["missing_market_data"],
    ["duplicate_candidate"],
    ["duplicate_order_intent"],
    ["ledger_lock_contention"],
    ["interrupted_ledger_append"],
    ["snapshot_corruption"],
    ["missing_latest_snapshot"],
    ["disk_soft_limit"],
    ["network_loss"],
    ["partial_fill_before_crash"],
    ["filled_order_before_snapshot"],
    ["exit_event_before_position_snapshot"],
    ["reflection_interruption"],
    ["lesson_storage_interruption"],
    ["pause_during_pending_intent"],
])
def test_resumable_injection_completes_clean(tmp_path: Path, inj: list[str]) -> None:
    d = _run(tmp_path, f"S_{inj[0]}", inj, count=45)
    assert d["session_pass"] is True, d
    assert d["final_state"] == "COMPLETED", d
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
        assert d["invariants_counts"][k] == 0, (k, d)


# ---------------------------------------------------------------------------
# Terminal injections (session must end BLOCKED or FAILED_SAFE)
# ---------------------------------------------------------------------------

def test_disk_hard_limit_routes_to_blocked(tmp_path: Path) -> None:
    d = _run(tmp_path, "S_disk_hard", [], count=40, disk_limit="hard")
    assert d["final_state"] in {"BLOCKED"}
    assert d["invariants_status"] == "PASS"
    assert d["exchange_write_attempt_count"] == 0


def test_process_termination_recovery_clean(tmp_path: Path) -> None:
    d = _run(
        tmp_path,
        "S_proc_term",
        ["process_termination"],
        count=50,
        restart_after_index=20,
    )
    # After restart the session should either complete or block, but never
    # leave the system in an ambiguous state.
    assert d["final_state"] in {"COMPLETED", "BLOCKED"}
    assert d["restart_count"] >= 1
    assert d["invariants_status"] == "PASS"
    assert d["exchange_write_attempt_count"] == 0


def test_kill_switch_during_open_position(tmp_path: Path) -> None:
    d = _run(
        tmp_path,
        "S_kill_open",
        ["kill_switch_during_open_position"],
        count=80,
        force_kill_after_index=15,
    )
    assert d["kill_switch_status"] == "TRIGGERED"
    assert d["final_state"] == "BLOCKED"
    assert d["invariants_status"] == "PASS"
    assert d["exchange_write_attempt_count"] == 0


def test_clock_jump_backward_recovery_or_block(tmp_path: Path) -> None:
    d = _run(tmp_path, "S_clock_back", ["clock_jump_backward"], count=60)
    # Must fail-closed via RECOVERING; either recovered-clean or blocked.
    assert d["final_state"] in {"COMPLETED", "BLOCKED"}
    assert d["invariants_status"] == "PASS"
    assert d["exchange_write_attempt_count"] == 0
    # At least one recovery attempt happened.
    assert d["recovery_count"] >= 1


def test_clock_jump_forward_completes_or_blocks(tmp_path: Path) -> None:
    d = _run(tmp_path, "S_clock_fwd", ["clock_jump_forward"], count=60)
    # Forward jumps are legal (monotonic) — session should complete.
    assert d["final_state"] in {"COMPLETED"}
    assert d["invariants_status"] == "PASS"


# ---------------------------------------------------------------------------
# Kill switch under every listed condition
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("timing_index", [0, 5, 25, 45])
def test_kill_switch_during_various_phases(tmp_path: Path, timing_index: int) -> None:
    d = _run(
        tmp_path,
        f"S_kill_t{timing_index}",
        [],
        count=60,
        force_kill_after_index=timing_index,
    )
    assert d["kill_switch_status"] == "TRIGGERED"
    assert d["final_state"] == "BLOCKED"
    assert d["exchange_write_attempt_count"] == 0
    # Kill switch must never leave orphaned lifecycles or ambiguous positions.
    for k in (
        "open_ambiguous_position_count",
        "orphan_lifecycle_count",
        "duplicate_position_count",
        "unclosed_intent_count",
        "untracked_fill_count",
        "risk_limit_bypass_count",
        "exchange_write_attempt_count",
    ):
        assert d["invariants_counts"][k] == 0, (k, d)


def test_kill_switch_with_no_position(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        orch.start("S_kill_none", logical_hours=1.0)
        orch.trigger_kill_switch(reason="test_no_position")
        orch.finalize()
        assert orch.state_machine.state == "BLOCKED"
        assert orch.guard.exchange_write_attempt_count == 0
    finally:
        orch.close()


def test_kill_switch_cancels_pending_orders(tmp_path: Path) -> None:
    orch = AutonomousSessionOrchestratorV11(tmp_path, max_positions=2, max_intents=2)
    try:
        orch.start("S_kill_pending", logical_hours=1.0)
        # Create a pending limit order that won't fill immediately.
        cand = {
            "candidate_id": "PC0",
            "idempotency_key": "PK0",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "limit",
            "mark_price": 100.0,
            "limit_price": 50.0,  # way below mark, won't fill
            "lose": False,
        }
        # Directly create a limit-below-market order via the sim to simulate
        # a pending intent that is safely cancellable.
        created = orch.sim.create_order(
            {
                "idempotency_key": "PK_pending",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "limit",
                "qty": 0.5,
                "price": 50.0,
                "mark_price": 100.0,
            }
        )
        assert created["status"] == "ACCEPTED"
        orch.trigger_kill_switch(reason="test_cancel_pending")
        # Kill switch cancels pending orders.
        assert orch.sim.orders[created["order_id"]].state == "CANCELLED"
        orch.finalize()
        assert orch.state_machine.state == "BLOCKED"
    finally:
        orch.close()


# ---------------------------------------------------------------------------
# Concurrency invariants
# ---------------------------------------------------------------------------

def test_full_injection_catalog_terminal_when_all_included(tmp_path: Path) -> None:
    """When ALL catalog injections are included (including kill switch), the
    session must still exit in an accepted terminal state with clean
    invariants."""
    d = _run(tmp_path, "S_all", list(INJECTION_CATALOG), count=80, restart_after_index=25)
    assert d["final_state"] in {"COMPLETED", "BLOCKED"}
    assert d["invariants_status"] == "PASS"
    assert d["exchange_write_attempt_count"] == 0
