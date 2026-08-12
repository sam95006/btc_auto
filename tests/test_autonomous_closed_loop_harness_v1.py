"""Autonomous Closed-Loop Harness V1 — fixture plumbing only."""
from __future__ import annotations

import os

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

import pytest

from backend.nexus_autonomy.closed_loop_harness_v1 import ClosedLoopHarness, Lifecycle, run_harness


def test_invalid_transition_fail_closed():
    lc = Lifecycle(lifecycle_id="x")
    with pytest.raises(ValueError):
        lc.transition("SIMULATED_OPEN", reason="bad", evidence={}, idempotency_key="k")


def test_scenario_matrix_all_pass():
    result = run_harness()
    assert result["recommendation"] == "NEXUS_AUTONOMOUS_HARNESS_V1_PASS"
    assert result["scenario_count"] == 8
    assert result["scenario_pass_count"] == 8
    assert result["scenario_failure_count"] == 0
    assert result["exchange_write_attempt_count"] == 0
    assert result["demo_order_count"] == 0
    assert result["real_learning_claimed"] is False
    assert result["label"] == "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"


def test_good_process_loss_not_broad_suppress():
    h = ClosedLoopHarness()
    r = h.run_happy_path({"candidate_id": "L1", "idempotency_key": "L1"}, pnl=-2)
    assert r["classification"] == "GOOD_PROCESS_LOSS"
    r2 = h.run_happy_path({"candidate_id": "L2", "idempotency_key": "L2"}, pnl=1)
    assert r2["status"] == "COMPLETE"


def test_hard_risk_rejects_leverage_and_stop_widen():
    h = ClosedLoopHarness()
    r = h.run_happy_path(
        {
            "candidate_id": "R1",
            "idempotency_key": "R1",
            "ai_request": {"requested_actions": ["risk_increase"]},
        },
        pnl=0,
    )
    assert r["status"] == "BLOCKED"
    assert r["risk"]["order_or_policy_mutation"] is False
