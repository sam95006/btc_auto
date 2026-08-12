"""Security boundary — no real exchange write may ever occur."""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_execution import security_boundary
from backend.nexus_execution.execution_simulator_v1_1 import (
    AutonomousExecutionSimulatorV11,
    BarContext,
)
from backend.nexus_execution.instrument import DEFAULT_INSTRUMENTS


class _FakeExchangeClient:
    """Represents ANY authenticated exchange-write client that must never fire."""

    def create_order(self, *a, **k):  # pragma: no cover — must never be called
        raise AssertionError("real create_order invoked")

    def cancel_order(self, *a, **k):  # pragma: no cover
        raise AssertionError("real cancel_order invoked")

    def transfer(self, *a, **k):  # pragma: no cover
        raise AssertionError("real transfer invoked")


def test_traps_intercept_forbidden_methods():
    security_boundary.reset_counters()
    client = _FakeExchangeClient()
    trapped = security_boundary.install_exchange_write_traps([client])
    assert trapped >= 3
    with pytest.raises(security_boundary.ExchangeWriteAttempted):
        client.create_order(symbol="BTCUSDT")
    assert security_boundary.exchange_write_attempt_count() == 1


def test_simulator_never_triggers_traps_during_full_round_trip():
    security_boundary.reset_counters()
    client = _FakeExchangeClient()
    security_boundary.install_exchange_write_traps([client])
    sim = AutonomousExecutionSimulatorV11(max_positions=1, max_intents=1)
    spec = DEFAULT_INSTRUMENTS["BTCUSDT"]

    def bar(mark: Decimal, idx: int) -> BarContext:
        return BarContext(
            bar_index=idx,
            open_price=mark,
            high=mark + spec.tick_size * Decimal(20),
            low=mark - spec.tick_size * Decimal(20),
            close=mark,
            mark_price=mark,
            index_price=mark,
            bid=mark - spec.tick_size,
            ask=mark + spec.tick_size,
        )

    o = sim.create_order(
        {"idempotency_key": "SO", "symbol": "BTCUSDT", "side": "BUY", "order_type": "MARKET", "qty": Decimal("0.1")},
        mark_price=Decimal("100"),
    )
    sim.try_fill(o["order_id"], bar(Decimal("100"), 1))
    e = sim.create_order(
        {"idempotency_key": "SE", "symbol": "BTCUSDT", "side": "SELL", "order_type": "MARKET", "qty": Decimal("0.1"), "reduce_only": True},
        mark_price=Decimal("101"),
    )
    sim.try_fill(e["order_id"], bar(Decimal("101"), 2))
    security_boundary.assert_no_exchange_write()
    assert security_boundary.exchange_write_attempt_count() == 0
    assert security_boundary.demo_order_count() == 0
    assert security_boundary.is_mainnet() is False
    assert security_boundary.is_real_money() is False


def test_execution_mode_banner_is_simulated():
    assert security_boundary.EXECUTION_MODE == "SIMULATED_NO_EXCHANGE_WRITE"
