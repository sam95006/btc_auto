"""Tests for DEMO_AUTONOMOUS_6H_BOUNDED_VALIDATION helpers."""
from __future__ import annotations

from backend.nexus_demo_execution.cost_entry_gate import evaluate_cost_gate
from backend.nexus_demo_execution.session_limits import SESSION_DURATION_SEC, SESSION_GATE_NAME
from backend.nexus_demo_execution.session_mistake_memory import SessionMistakeMemory


def test_session_duration_is_six_hours():
    assert SESSION_DURATION_SEC == 6 * 60 * 60
    assert SESSION_GATE_NAME == "DEMO_AUTONOMOUS_6H_BOUNDED_VALIDATION"


def test_cost_gate_blocks_unknown_fee():
    r = evaluate_cost_gate(
        entry_price=100,
        stop_loss=99,
        take_profit=102,
        qty=1,
        side="Buy",
        fee_rate=None,
        funding_rate=None,
        slippage_bps=1,
    )
    assert r.allowed is False
    assert r.reason == "FEE_RATE_UNKNOWN"


def test_cost_gate_blocks_fee_churn():
    r = evaluate_cost_gate(
        entry_price=100,
        stop_loss=99.9,
        take_profit=100.05,
        qty=1,
        side="Buy",
        fee_rate=0.00055,
        funding_rate=None,
        slippage_bps=5,
    )
    assert r.allowed is False
    assert "BLOCK_COST_DOMINATED" in r.reason


def test_cost_gate_passes_wide_edge():
    r = evaluate_cost_gate(
        entry_price=100,
        stop_loss=98,
        take_profit=103,
        qty=1,
        side="Buy",
        fee_rate=0.00055,
        funding_rate=0.0001,
        slippage_bps=1,
    )
    assert r.allowed is True


def test_mistake_memory_decision_delta():
    mem = SessionMistakeMemory()
    action = mem.remember_from_outcome(
        trade_case_id="baseline-smoke",
        candidate={"symbol": "BTCUSDT", "direction": "Sell", "strategy": "SMOKE_MOMENTUM_15M", "regime": "TREND_DOWN"},
        outcome="GOOD_PROCESS_LOSS",
        cost_labels=["fee_churn_candidate", "direction_correct_but_net_loss"],
    )
    assert action == "BLOCK_COST_DOMINATED_SETUP"
    delta = mem.apply(
        candidate={
            "candidate_id": "c1",
            "symbol": "BTCUSDT",
            "direction": "Sell",
            "strategy": "SMOKE_MOMENTUM_15M",
            "regime": "TREND_DOWN",
        },
        before_score=1.0,
    )
    assert delta["after_verdict"] == "BLOCK"
    assert delta["guard_action"] in {"BLOCK_COST_DOMINATED_SETUP", "EXACT_SETUP_COOLDOWN"}
