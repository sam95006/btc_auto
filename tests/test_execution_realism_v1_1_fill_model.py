"""V1.1 fill model — conservative deterministic semantics."""
from __future__ import annotations

import os
from decimal import Decimal

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_execution import security_boundary
from backend.nexus_execution.execution_simulator_v1_1 import (
    AutonomousExecutionSimulatorV11,
    BarContext,
)
from backend.nexus_execution.instrument import DEFAULT_INSTRUMENTS


def _bar(symbol: str, mark: Decimal, *, bar_index: int = 1, stop=None, target=None) -> BarContext:
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
        same_bar_stop=stop,
        same_bar_target=target,
    )


def _sim() -> AutonomousExecutionSimulatorV11:
    security_boundary.reset_counters()
    return AutonomousExecutionSimulatorV11(max_positions=1, max_intents=1)


def test_market_buy_fills_at_ask():
    sim = _sim()
    r = sim.create_order(
        {
            "idempotency_key": "K1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        mark_price=Decimal("100"),
    )
    assert r["status"] == "ACCEPTED"
    out = sim.try_fill(r["order_id"], _bar("BTCUSDT", Decimal("100")))
    assert out["status"] == "FILLED"
    order = sim.orders[r["order_id"]]
    assert order.avg_fill_price == Decimal("100.1")


def test_limit_buy_requires_trade_through_one_tick():
    sim = _sim()
    # Bar touches the limit but never trades through.
    r = sim.create_order(
        {
            "idempotency_key": "K2",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "qty": Decimal("0.1"),
            "price": Decimal("100.0"),
        },
        mark_price=Decimal("100"),
    )
    assert r["status"] == "ACCEPTED"
    spec = DEFAULT_INSTRUMENTS["BTCUSDT"]
    # low equals limit -> touch, not trade-through -> UNFILLED
    bar = BarContext(
        bar_index=1,
        open_price=Decimal("100"),
        high=Decimal("100.05"),
        low=Decimal("100.0"),  # touch only
        close=Decimal("100"),
        mark_price=Decimal("100"),
        index_price=Decimal("100"),
        bid=Decimal("100") - spec.tick_size,
        ask=Decimal("100") + spec.tick_size,
    )
    out = sim.try_fill(r["order_id"], bar)
    assert out["status"] == "UNFILLED", out

    # Now trade through by exactly 1 tick.
    bar2 = BarContext(
        bar_index=2,
        open_price=Decimal("100"),
        high=Decimal("100.05"),
        low=Decimal("99.9"),  # limit - 1 tick
        close=Decimal("100"),
        mark_price=Decimal("100"),
        index_price=Decimal("100"),
        bid=Decimal("100") - spec.tick_size,
        ask=Decimal("100") + spec.tick_size,
    )
    out2 = sim.try_fill(r["order_id"], bar2)
    assert out2["status"] == "FILLED"


def test_same_bar_stop_and_target_is_blocked_ambiguous():
    sim = _sim()
    r = sim.create_order(
        {
            "idempotency_key": "AMB",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "STOP_MARKET",
            "qty": Decimal("0.1"),
            "stop_price": Decimal("99.5"),
        },
        mark_price=Decimal("100"),
    )
    assert r["status"] == "ACCEPTED"
    bar = _bar("BTCUSDT", Decimal("100"), stop=Decimal("99.5"), target=Decimal("100.5"))
    out = sim.try_fill(r["order_id"], bar)
    assert out["status"] == "BLOCKED_AMBIGUOUS"
    assert sim.orders[r["order_id"]].state == "REJECTED"


def test_market_partial_then_complete_reconciles():
    sim = _sim()
    r = sim.create_order(
        {
            "idempotency_key": "PART",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.100"),
        },
        mark_price=Decimal("100"),
    )
    p1 = sim.try_fill(r["order_id"], _bar("BTCUSDT", Decimal("100")), partial_ratio=Decimal("0.5"))
    assert p1["status"] == "PARTIALLY_FILLED"
    p2 = sim.try_fill(r["order_id"], _bar("BTCUSDT", Decimal("100"), bar_index=2))
    assert p2["status"] == "FILLED"
    order = sim.orders[r["order_id"]]
    assert order.filled_qty == order.intent.qty


def test_market_sell_fills_at_bid():
    sim = _sim()
    r = sim.create_order(
        {
            "idempotency_key": "SELL",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        mark_price=Decimal("100"),
    )
    sim.try_fill(r["order_id"], _bar("BTCUSDT", Decimal("100")))
    assert sim.orders[r["order_id"]].avg_fill_price == Decimal("99.9")


def test_stop_market_triggers_on_mark_price_beyond_stop():
    sim = _sim()
    # open a long first
    o = sim.create_order(
        {"idempotency_key": "L", "symbol": "BTCUSDT", "side": "BUY", "order_type": "MARKET", "qty": Decimal("0.1")},
        mark_price=Decimal("100"),
    )
    sim.try_fill(o["order_id"], _bar("BTCUSDT", Decimal("100")))
    # sell stop below
    s = sim.create_order(
        {
            "idempotency_key": "STOP",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "STOP_MARKET",
            "qty": Decimal("0.1"),
            "stop_price": Decimal("99.0"),
            "reduce_only": True,
        },
        mark_price=Decimal("100"),
    )
    out = sim.try_fill(s["order_id"], _bar("BTCUSDT", Decimal("98.0"), bar_index=2))
    assert out["status"] == "FILLED"


def test_expired_limit_transitions_to_expired():
    sim = _sim()
    r = sim.create_order(
        {
            "idempotency_key": "EXP",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "qty": Decimal("0.1"),
            "price": Decimal("90.0"),
            "expires_at_bar": 1,
        },
        mark_price=Decimal("100"),
    )
    out = sim.try_fill(r["order_id"], _bar("BTCUSDT", Decimal("100"), bar_index=2))
    assert out["status"] == "EXPIRED"
    assert sim.orders[r["order_id"]].state == "EXPIRED"


def test_stale_mark_price_rejects_bar():
    sim = _sim()
    r = sim.create_order(
        {
            "idempotency_key": "STALE",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        mark_price=Decimal("100"),
    )
    spec = DEFAULT_INSTRUMENTS["BTCUSDT"]
    bar = BarContext(
        bar_index=1,
        open_price=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        mark_price=Decimal("100"),
        index_price=Decimal("100"),
        bid=Decimal("100") - spec.tick_size,
        ask=Decimal("100") + spec.tick_size,
        mark_price_age_ms=20_000,
    )
    out = sim.try_fill(r["order_id"], bar)
    assert out["status"] == "REJECTED"
    assert out["reason"] == "STALE_MARK_PRICE"


def test_missing_index_price_rejects_bar():
    sim = _sim()
    r = sim.create_order(
        {
            "idempotency_key": "NOIDX",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        mark_price=Decimal("100"),
    )
    spec = DEFAULT_INSTRUMENTS["BTCUSDT"]
    bar = BarContext(
        bar_index=1,
        open_price=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        mark_price=Decimal("100"),
        index_price=None,
        bid=Decimal("100") - spec.tick_size,
        ask=Decimal("100") + spec.tick_size,
    )
    out = sim.try_fill(r["order_id"], bar)
    assert out["status"] == "REJECTED"
    assert out["reason"] == "INDEX_PRICE_MISSING"
