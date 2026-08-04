"""Immutable risk gates — must never be bypassable via requested_actions."""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_execution import security_boundary
from backend.nexus_execution.execution_simulator_v1_1 import AutonomousExecutionSimulatorV11
from backend.nexus_execution.risk_gates import (
    FORBIDDEN_ACTIONS,
    RiskLimits,
    RiskState,
    evaluate_intent,
)


def test_leverage_ceiling_enforced_at_construction():
    with pytest.raises(ValueError):
        AutonomousExecutionSimulatorV11(leverage=51)


def test_leverage_100_forbidden_by_ctor():
    # Also disallowed by the explicit FORBIDDEN_LEVERAGE_VALUES gate.
    with pytest.raises(ValueError):
        AutonomousExecutionSimulatorV11(leverage=100)


def test_cross_margin_construction_forbidden():
    with pytest.raises(ValueError):
        RiskLimits(max_positions=1, max_intents=1, leverage=25, margin_usdt=Decimal("20"), margin_mode="CROSS")


def test_forbidden_actions_reject_intent():
    limits = RiskLimits(max_positions=2, max_intents=2, leverage=25, margin_usdt=Decimal("20"))
    state = RiskState(open_position_count=0, pending_intent_count=0)
    for action in sorted(FORBIDDEN_ACTIONS):
        decision = evaluate_intent(
            limits,
            state,
            {"symbol": "BTCUSDT", "requested_actions": [action]},
        )
        assert not decision.allowed
        assert decision.reason == "HARD_RISK_OVERRIDE_REJECTED"
        assert decision.order_or_policy_mutation is False


def test_max_positions_and_intents_enforced():
    security_boundary.reset_counters()
    sim = AutonomousExecutionSimulatorV11(max_positions=1, max_intents=1)
    r1 = sim.create_order(
        {"idempotency_key": "A", "symbol": "BTCUSDT", "side": "BUY", "order_type": "MARKET", "qty": Decimal("0.1")},
        mark_price=Decimal("100"),
    )
    r2 = sim.create_order(
        {"idempotency_key": "B", "symbol": "BTCUSDT", "side": "BUY", "order_type": "MARKET", "qty": Decimal("0.1")},
        mark_price=Decimal("100"),
    )
    assert r1["status"] == "ACCEPTED"
    assert r2["status"] == "REJECTED"
    assert r2["reason"] == "MAX_INTENTS"


def test_cross_margin_via_intent_rejected():
    security_boundary.reset_counters()
    sim = AutonomousExecutionSimulatorV11()
    r = sim.create_order(
        {
            "idempotency_key": "X",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
            "margin_mode": "CROSS",
        },
        mark_price=Decimal("100"),
    )
    assert r["status"] == "REJECTED"
    assert r["reason"] == "CROSS_MARGIN_FORBIDDEN"


def test_tick_and_step_and_notional_violations():
    security_boundary.reset_counters()
    sim = AutonomousExecutionSimulatorV11()
    off_tick = sim.create_order(
        {
            "idempotency_key": "T",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "qty": Decimal("0.1"),
            "price": Decimal("100.03"),  # tick=0.1 -> off tick
        },
        mark_price=Decimal("100"),
    )
    assert off_tick["status"] == "REJECTED"
    assert off_tick["reason"] == "TICK_SIZE_VIOLATION"

    off_step = sim.create_order(
        {"idempotency_key": "S", "symbol": "BTCUSDT", "side": "BUY", "order_type": "MARKET", "qty": Decimal("0.0015")},
        mark_price=Decimal("100"),
    )
    assert off_step["status"] == "REJECTED"
    assert off_step["reason"] == "QUANTITY_STEP_VIOLATION"

    tiny = sim.create_order(
        {"idempotency_key": "N", "symbol": "BTCUSDT", "side": "BUY", "order_type": "MARKET", "qty": Decimal("0.001")},
        mark_price=Decimal("0.001"),
    )
    assert tiny["status"] == "REJECTED"
    assert tiny["reason"] == "MIN_NOTIONAL_VIOLATION"
