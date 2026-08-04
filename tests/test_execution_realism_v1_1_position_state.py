"""Position state machine + reduce-only invariants."""
from __future__ import annotations

import os
from decimal import Decimal

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_execution import security_boundary
from backend.nexus_execution.contracts import POSITION_TRANSITIONS
from backend.nexus_execution.execution_simulator_v1_1 import (
    AutonomousExecutionSimulatorV11,
    BarContext,
)
from backend.nexus_execution.instrument import DEFAULT_INSTRUMENTS


def _bar(symbol: str, mark: Decimal, *, bar_index: int = 1) -> BarContext:
    spec = DEFAULT_INSTRUMENTS[symbol]
    return BarContext(
        bar_index=bar_index,
        open_price=mark,
        high=mark + spec.tick_size * Decimal(20),
        low=mark - spec.tick_size * Decimal(20),
        close=mark,
        mark_price=mark,
        index_price=mark,
        bid=mark - spec.tick_size,
        ask=mark + spec.tick_size,
    )


def _sim() -> AutonomousExecutionSimulatorV11:
    security_boundary.reset_counters()
    return AutonomousExecutionSimulatorV11(max_positions=2, max_intents=2)


def test_open_close_round_trip_transitions():
    sim = _sim()
    o = sim.create_order(
        {"idempotency_key": "O", "symbol": "BTCUSDT", "side": "BUY", "order_type": "MARKET", "qty": Decimal("0.1")},
        mark_price=Decimal("100"),
    )
    opened = sim.try_fill(o["order_id"], _bar("BTCUSDT", Decimal("100")))
    pid = opened["position_id"]
    assert sim.positions[pid].state == "OPEN"

    e = sim.create_order(
        {"idempotency_key": "E", "symbol": "BTCUSDT", "side": "SELL", "order_type": "MARKET", "qty": Decimal("0.1"), "reduce_only": True},
        mark_price=Decimal("101"),
    )
    sim.try_fill(e["order_id"], _bar("BTCUSDT", Decimal("101"), bar_index=2))
    pos = sim.positions[pid]
    assert pos.state == "CLOSED"
    assert pos.qty == Decimal(0)


def test_partial_reduction_returns_to_open_state():
    sim = _sim()
    o = sim.create_order(
        {"idempotency_key": "O", "symbol": "BTCUSDT", "side": "BUY", "order_type": "MARKET", "qty": Decimal("0.2")},
        mark_price=Decimal("100"),
    )
    opened = sim.try_fill(o["order_id"], _bar("BTCUSDT", Decimal("100")))
    pid = opened["position_id"]
    e = sim.create_order(
        {"idempotency_key": "E1", "symbol": "BTCUSDT", "side": "SELL", "order_type": "MARKET", "qty": Decimal("0.1"), "reduce_only": True},
        mark_price=Decimal("101"),
    )
    sim.try_fill(e["order_id"], _bar("BTCUSDT", Decimal("101"), bar_index=2))
    pos = sim.positions[pid]
    assert pos.state == "OPEN"
    assert pos.qty == Decimal("0.1")


def test_reduce_only_without_position_rejects():
    sim = _sim()
    r = sim.create_order(
        {"idempotency_key": "R", "symbol": "BTCUSDT", "side": "SELL", "order_type": "MARKET", "qty": Decimal("0.1"), "reduce_only": True},
        mark_price=Decimal("100"),
    )
    assert r["status"] == "REJECTED"


def test_forced_liquidation_transitions_position():
    sim = _sim()
    o = sim.create_order(
        {"idempotency_key": "O", "symbol": "BTCUSDT", "side": "BUY", "order_type": "MARKET", "qty": Decimal("0.1")},
        mark_price=Decimal("100"),
    )
    opened = sim.try_fill(o["order_id"], _bar("BTCUSDT", Decimal("100")))
    pid = opened["position_id"]
    liq = sim.force_liquidation(pid, mark_price=Decimal("90"))
    assert liq["status"] == "LIQUIDATED_SIMULATED"
    assert sim.positions[pid].state == "LIQUIDATED_SIMULATED"
    assert sim.positions[pid].qty == Decimal(0)


def test_position_transitions_are_registered():
    # Ensure OPEN->REDUCING->OPEN and OPEN->CLOSED are all in the allowed set.
    for t in [("OPEN", "REDUCING"), ("REDUCING", "OPEN"), ("OPEN", "CLOSED"), ("REDUCING", "CLOSED")]:
        assert t in POSITION_TRANSITIONS
