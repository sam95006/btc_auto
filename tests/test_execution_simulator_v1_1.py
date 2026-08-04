"""Deterministic property/fuzz tests for Autonomous Execution Simulator V1.1.

Frozen seeds. Minimum 10,000 generated execution scenarios.
No exchange writes. EXCHANGE_WRITE=false.
"""
from __future__ import annotations

import os
import random
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"

import pytest

from backend.nexus_autonomy.execution_models_v1_1 import FILL_POLICY_DOC, InstrumentSpec
from backend.nexus_autonomy.execution_simulator_v1_1 import (
    MAX_LEVERAGE_CEILING,
    AutonomousExecutionSimulatorV1_1,
)

FROZEN_SEEDS = (42, 7, 99, 12345, 20260805)
SCENARIOS_PER_SEED = 2000  # 5 * 2000 = 10_000
TOTAL_TARGET = 10_000


def _bounded_sim(**kwargs) -> AutonomousExecutionSimulatorV1_1:
    defaults = dict(max_positions=1, max_intents=1, leverage=25, margin_usdt=20.0)
    defaults.update(kwargs)
    return AutonomousExecutionSimulatorV1_1(**defaults)


def _immutable_sim(**kwargs) -> AutonomousExecutionSimulatorV1_1:
    defaults = dict(max_positions=2, max_intents=2, leverage=25, margin_usdt=20.0)
    defaults.update(kwargs)
    return AutonomousExecutionSimulatorV1_1(**defaults)


def test_leverage_100x_and_cross_forbidden():
    with pytest.raises(ValueError):
        AutonomousExecutionSimulatorV1_1(leverage=100)
    with pytest.raises(ValueError):
        AutonomousExecutionSimulatorV1_1(leverage=51)
    sim = _bounded_sim()
    r = sim.create_order(
        {
            "idempotency_key": "x",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "CROSS",
        }
    )
    assert r["status"] == "REJECTED"
    assert r["reason"] == "CROSS_MARGIN_FORBIDDEN"


def test_fill_policy_touch_alone_insufficient():
    sim = _bounded_sim()
    o = sim.create_order(
        {
            "idempotency_key": "lim",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "limit",
            "qty": 0.1,
            "price": 100.0,
            "mark_price": 100.5,
            "margin_mode": "ISOLATED",
        }
    )
    assert o["status"] == "ACCEPTED"
    # Touch exactly at limit — must NOT fill
    r = sim.try_fill(
        o["order_id"],
        market_bid=99.9,
        market_ask=100.1,
        last_price=100.0,
        path_low=100.0,
        path_high=100.2,
        mark_price=100.0,
        index_price=100.0,
    )
    assert r["status"] == "UNFILLED"
    # Trade-through by 1 tick → fill
    r2 = sim.try_fill(
        o["order_id"],
        market_bid=99.8,
        market_ask=100.1,
        last_price=99.9,
        path_low=99.9,
        path_high=100.2,
        mark_price=99.9,
        index_price=99.9,
        opposite_volume=1.0,
    )
    assert r2["status"] in {"FILLED", "PARTIALLY_FILLED"}
    assert "TOUCH_ALONE_INSUFFICIENT" in FILL_POLICY_DOC
    assert "CANDLE_TOUCH_NEVER_EQUALS_FILL" in FILL_POLICY_DOC


def test_duplicate_intent_never_duplicate_position():
    sim = _bounded_sim()
    a = sim.create_order(
        {
            "idempotency_key": "dup",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "market",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    b = sim.create_order(
        {
            "idempotency_key": "dup",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "market",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    assert a["status"] == "ACCEPTED"
    assert b["status"] == "DUPLICATE_IGNORED"
    sim.try_fill(
        a["order_id"],
        market_bid=99.9,
        market_ask=100.1,
        last_price=100,
        path_low=99,
        path_high=101,
        mark_price=100,
        index_price=100,
    )
    assert len([p for p in sim.positions.values() if p.state in {"OPEN", "OPENING"}]) == 1


def test_reduce_only_never_increases_exposure():
    sim = _bounded_sim()
    o = sim.create_order(
        {
            "idempotency_key": "open1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "market",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    sim.try_fill(
        o["order_id"],
        market_bid=99.9,
        market_ask=100.1,
        last_price=100,
        path_low=99,
        path_high=101,
        mark_price=100,
        index_price=100,
    )
    pos = next(iter(sim.positions.values()))
    exp0 = pos.qty
    # reduce-only BUY while long → reject
    bad = sim.create_order(
        {
            "idempotency_key": "bad_ro",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "market",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
            "reduce_only": True,
        }
    )
    assert bad["status"] == "REJECTED"
    assert pos.qty == exp0
    # proper reduce
    cl = sim.create_order(
        {
            "idempotency_key": "close1",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "market",
            "qty": 0.1,
            "mark_price": 101,
            "margin_mode": "ISOLATED",
            "reduce_only": True,
        }
    )
    assert cl["status"] == "ACCEPTED"
    r = sim.try_fill(
        cl["order_id"],
        market_bid=100.9,
        market_ask=101.1,
        last_price=101,
        path_low=100,
        path_high=102,
        mark_price=101,
        index_price=101,
    )
    assert r["status"] == "FILLED"
    assert r["close"]["residual_qty"] == 0
    assert r["close"]["cost_identity_ok"] is True
    assert abs(r["close"]["gross_pnl"] - r["close"]["all_costs"] - r["close"]["net_pnl"]) < 1e-9


def test_partial_fills_reconcile():
    sim = _bounded_sim(qty_step=0.001)
    o = sim.create_order(
        {
            "idempotency_key": "part",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "limit",
            "qty": 0.1,
            "price": 100.0,
            "mark_price": 100.5,
            "margin_mode": "ISOLATED",
            "queue_ahead_qty": 0.0,
        }
    )
    r1 = sim.try_fill(
        o["order_id"],
        market_bid=99.8,
        market_ask=100.1,
        last_price=99.9,
        path_low=99.8,
        path_high=100.2,
        mark_price=99.9,
        index_price=99.9,
        partial_ratio=0.4,
        opposite_volume=10.0,
    )
    assert r1["status"] == "PARTIALLY_FILLED"
    assert r1["reconcile_ok"] is True
    order = sim.orders[o["order_id"]]
    assert abs((order.filled_qty + order.remaining_qty) - order.qty) < 1e-9
    r2 = sim.try_fill(
        o["order_id"],
        market_bid=99.7,
        market_ask=100.1,
        last_price=99.8,
        path_low=99.7,
        path_high=100.2,
        mark_price=99.8,
        index_price=99.8,
        opposite_volume=10.0,
    )
    assert r2["status"] == "FILLED"
    assert abs(order.filled_qty - order.qty) < 1e-9
    assert order.remaining_qty == 0


def test_order_expiry_and_cancel_replace():
    sim = _bounded_sim(now_ms=1000)
    o = sim.create_order(
        {
            "idempotency_key": "exp",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "limit",
            "qty": 0.1,
            "price": 90.0,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
            "time_in_force": "GTD",
            "expires_at_ms": 2000,
        }
    )
    assert o["status"] == "ACCEPTED"
    sim.advance_time(1500)
    assert sim.orders[o["order_id"]].state == "EXPIRED"

    o2 = sim.create_order(
        {
            "idempotency_key": "rep",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "limit",
            "qty": 0.1,
            "price": 95.0,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    rep = sim.replace_order(o2["order_id"], {"price": 96.0, "mark_price": 100, "index_price": 100})
    assert rep["status"] == "REPLACED"
    assert rep["new"]["status"] == "ACCEPTED"
    assert sim.orders[o2["order_id"]].state == "REPLACED"


def test_stop_widening_and_martingale_forbidden():
    sim = _bounded_sim()
    bad = sim.create_order(
        {
            "idempotency_key": "mg",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
            "requested_actions": ["martingale"],
        }
    )
    assert bad["reason"] == "HARD_RISK_OVERRIDE_REJECTED"
    o = sim.create_order(
        {
            "idempotency_key": "st",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "stop-market",
            "qty": 0.1,
            "mark_price": 100,
            "stop_price": 95.0,
            "margin_mode": "ISOLATED",
            "reduce_only": False,
        }
    )
    # Without position reduce_only false is ok for stop entry; widen check on replace
    # First need accepted working stop — max intents 1 so ok
    if o["status"] == "ACCEPTED":
        # open position first in another sim for widen test
        pass
    sim2 = _bounded_sim()
    open_o = sim2.create_order(
        {
            "idempotency_key": "o",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "market",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    sim2.try_fill(
        open_o["order_id"],
        market_bid=99.9,
        market_ask=100.1,
        last_price=100,
        path_low=99,
        path_high=101,
        mark_price=100,
        index_price=100,
    )
    st = sim2.create_order(
        {
            "idempotency_key": "stop",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "stop-market",
            "qty": 0.1,
            "mark_price": 100,
            "stop_price": 95.0,
            "margin_mode": "ISOLATED",
            "reduce_only": True,
        }
    )
    assert st["status"] == "ACCEPTED"
    widen = sim2.replace_order(st["order_id"], {"stop_price": 90.0, "mark_price": 100})
    assert widen["status"] == "REJECTED"
    assert widen["reason"] == "STOP_WIDENING_FORBIDDEN"


def test_ambiguous_same_bar_adverse_first():
    sim = _bounded_sim()
    o = sim.create_order(
        {
            "idempotency_key": "amb",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "stop-market",
            "qty": 0.1,
            "mark_price": 100,
            "stop_price": 99.5,
            "margin_mode": "ISOLATED",
        }
    )
    r = sim.try_fill(
        o["order_id"],
        market_bid=99.4,
        market_ask=100.1,
        last_price=100,
        path_low=99,
        path_high=101,
        mark_price=99.4,
        index_price=99.4,
        same_bar_stop=99.5,
        same_bar_target=100.5,
    )
    assert r["status"] == "BLOCKED_AMBIGUOUS"
    assert sim.exchange_write_attempt_count == 0


def test_instrument_halt_and_min_notional():
    sim = _bounded_sim(instrument_status="HALT")
    r = sim.create_order(
        {
            "idempotency_key": "h",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    assert r["reason"] == "INSTRUMENT_NOT_TRADING"
    sim2 = _bounded_sim(min_notional=50)
    r2 = sim2.create_order(
        {
            "idempotency_key": "n",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": 0.001,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    assert r2["reason"] == "LOT_OR_NOTIONAL"


def test_funding_debit_credit_and_liquidation_distance():
    sim = _bounded_sim()
    o = sim.create_order(
        {
            "idempotency_key": "f",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "market",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    fr = sim.try_fill(
        o["order_id"],
        market_bid=99.9,
        market_ask=100.1,
        last_price=100,
        path_low=99,
        path_high=101,
        mark_price=100,
        index_price=100,
    )
    pid = fr["position_id"]
    assert fr["liquidation_distance"] > 0
    debit = sim.apply_funding(pid, 0.0001, mark_price=100)
    assert debit["funding_delta"] > 0
    credit = sim.apply_funding(pid, -0.0001, mark_price=100)
    assert credit["funding_delta"] < 0
    mm = sim.check_maintenance_margin(pid, mark_price=100)
    assert "liquidation_distance" in mm
    assert mm["maintenance_margin"] > 0


def test_failed_orders_never_trades_and_no_exchange_write_methods():
    sim = _bounded_sim()
    sim.assert_no_exchange_write_api()
    r = sim.create_order(
        {
            "idempotency_key": "fail",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": 0.0,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    assert r["status"] == "REJECTED"
    assert len(sim.trades) == 0
    assert sim.exchange_write_attempt_count == 0
    # source scan: no forbidden method names as callables
    src = Path(__file__).resolve().parents[1] / "backend/nexus_autonomy/execution_simulator_v1_1.py"
    text = src.read_text(encoding="utf-8")
    for needle in (
        "def place_order_on_exchange",
        "def submit_bybit",
        "def authenticated_write",
        "def bybit_private_post",
    ):
        assert needle not in text


def test_max_positions_risk_limit():
    sim = _immutable_sim(max_positions=2, max_intents=2)
    for i in range(2):
        o = sim.create_order(
            {
                "idempotency_key": f"p{i}",
                "symbol": f"S{i}USDT",
                "side": "BUY",
                "order_type": "market",
                "qty": 0.1,
                "mark_price": 100,
                "margin_mode": "ISOLATED",
            }
        )
        assert o["status"] == "ACCEPTED"
        sim.try_fill(
            o["order_id"],
            market_bid=99.9,
            market_ask=100.1,
            last_price=100,
            path_low=99,
            path_high=101,
            mark_price=100,
            index_price=100,
        )
    third = sim.create_order(
        {
            "idempotency_key": "p2",
            "symbol": "S2USDT",
            "side": "BUY",
            "order_type": "market",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    assert third["reason"] == "MAX_POSITIONS"


def _run_scenario(rng: random.Random, scenario_id: int) -> dict:
    """One generated execution scenario; returns invariant check result."""
    max_pos = rng.choice([1, 2])
    max_int = rng.choice([1, 2])
    if max_pos == 1:
        max_int = 1
    sim = AutonomousExecutionSimulatorV1_1(
        max_positions=max_pos,
        max_intents=max_int,
        leverage=25,
        margin_usdt=20.0,
        tick_size=0.1,
        qty_step=0.001,
        min_notional=5.0,
        now_ms=scenario_id,
    )
    symbol = rng.choice(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    side = rng.choice(["BUY", "SELL"])
    order_type = rng.choice(["market", "limit", "stop-market"])
    mid = rng.uniform(50.0, 500.0)
    mid = round(mid / 0.1) * 0.1
    spread = 0.1
    bid = mid - spread / 2
    ask = mid + spread / 2
    qty = max(0.1, round(rng.uniform(0.1, 0.5) / 0.001) * 0.001)

    # occasional forbidden
    if rng.random() < 0.05:
        r = sim.create_order(
            {
                "idempotency_key": f"s{scenario_id}",
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "mark_price": mid,
                "margin_mode": rng.choice(["CROSS", "ISOLATED"]),
                "requested_actions": rng.choice([[], ["martingale"], ["averaging_down"], ["stop_widening"]]),
                "leverage": rng.choice([25, 50, 100]),
            }
        )
        if r.get("status") == "REJECTED":
            assert len(sim.trades) == 0
            return {"ok": True, "branch": "reject_policy"}

    req = {
        "idempotency_key": f"s{scenario_id}",
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "qty": qty,
        "mark_price": mid,
        "index_price": mid,
        "margin_mode": "ISOLATED",
        "latency_ms": rng.choice([0, 50, 200, 1000]),
        "queue_ahead_qty": rng.choice([0.0, 0.001, 0.01]),
    }
    if order_type == "limit":
        # passive or near
        offset = rng.choice([-0.5, -0.2, 0.0, 0.2, 0.5])
        req["price"] = round((mid + offset) / 0.1) * 0.1
    if order_type == "stop-market":
        if side == "SELL":
            req["stop_price"] = round((mid - rng.uniform(0.2, 2.0)) / 0.1) * 0.1
        else:
            req["stop_price"] = round((mid + rng.uniform(0.2, 2.0)) / 0.1) * 0.1

    created = sim.create_order(req)
    # duplicate
    dup = sim.create_order(req)
    assert dup["status"] in {"DUPLICATE_IGNORED", "REJECTED", "ACCEPTED"}
    if created["status"] != "ACCEPTED":
        assert len(sim.trades) == 0
        return {"ok": True, "branch": "create_reject"}

    oid = created["order_id"]
    # touch-only path (should usually not fill limits)
    path_mode = rng.choice(["touch", "through", "away", "ambiguous"])
    stop = req.get("stop_price")
    target = (stop + 1.0) if stop else mid + 1.0
    same_stop = same_tgt = None
    if path_mode == "touch" and order_type == "limit":
        px = req["price"]
        path_low = px
        path_high = px + 0.05
    elif path_mode == "through":
        if order_type == "limit":
            px = req["price"]
            if side == "BUY":
                path_low = px - 0.2
                path_high = px + 0.1
            else:
                path_low = px - 0.1
                path_high = px + 0.2
        else:
            path_low = mid - 2
            path_high = mid + 2
    elif path_mode == "ambiguous" and order_type == "stop-market":
        path_low = mid - 2
        path_high = mid + 2
        same_stop = stop
        same_tgt = target
    else:
        path_low = mid + 5
        path_high = mid + 6

    mark = rng.uniform(path_low, path_high) if path_low < path_high else mid
    fill = sim.try_fill(
        oid,
        market_bid=bid,
        market_ask=ask,
        last_price=mid,
        path_low=path_low,
        path_high=path_high,
        mark_price=mark,
        index_price=mid,
        same_bar_stop=same_stop,
        same_bar_target=same_tgt,
        partial_ratio=rng.choice([None, None, 0.3, 0.5, 0.8]),
        opposite_volume=rng.choice([0.0, 0.001, 0.01, 1.0, 10.0]),
        latency_adverse_bps=rng.choice([0.0, 0.5, 2.0]),
    )

    # invariants
    for o in sim.orders.values():
        assert o.qty >= 0
        assert o.filled_qty >= 0
        assert o.filled_qty <= o.qty + 1e-9
        assert abs((o.filled_qty + o.remaining_qty) - o.qty) < 1e-9
    for p in sim.positions.values():
        assert p.qty >= 0
        if p.state == "CLOSED":
            assert p.residual_qty == 0
            assert p.qty == 0
    assert sim.exchange_write_attempt_count == 0

    # reduce-only path sometimes
    if fill.get("status") in {"FILLED", "PARTIALLY_FILLED"} and rng.random() < 0.4:
        open_pos = [p for p in sim.positions.values() if p.state in {"OPEN", "OPENING"}]
        if open_pos:
            p = open_pos[0]
            close_side = "SELL" if p.side in {"LONG", "BUY"} else "BUY"
            # new intent
            c = sim.create_order(
                {
                    "idempotency_key": f"c{scenario_id}",
                    "symbol": p.symbol,
                    "side": close_side,
                    "order_type": "market",
                    "qty": p.qty,
                    "mark_price": mark,
                    "margin_mode": "ISOLATED",
                    "reduce_only": True,
                }
            )
            if c.get("status") == "ACCEPTED":
                cr = sim.try_fill(
                    c["order_id"],
                    market_bid=bid,
                    market_ask=ask,
                    last_price=mark,
                    path_low=mark - 1,
                    path_high=mark + 1,
                    mark_price=mark,
                    index_price=mark,
                )
                if cr.get("close"):
                    assert cr["close"]["residual_qty"] == 0
                    assert cr["close"]["cost_identity_ok"] is True
                    assert abs(cr["close"]["gross_pnl"] - cr["close"]["all_costs"] - cr["close"]["net_pnl"]) < 1e-9
            # reduce-only must not increase
            for p2 in sim.positions.values():
                assert p2.qty >= 0

    # funding sometimes
    for p in list(sim.positions.values()):
        if p.state in {"OPEN", "OPENING"} and rng.random() < 0.3:
            sim.apply_funding(p.position_id, rng.choice([-0.0001, 0.0001]), mark_price=mark)

    # expire sometimes
    if rng.random() < 0.1:
        sim.advance_time(10_000_000)

    assert sim.exchange_write_attempt_count == 0
    # failed/rejected never produced trades for that order if rejected at create
    return {"ok": True, "branch": fill.get("status", "na"), "report": sim.report()}


def test_property_fuzz_10000_scenarios():
    results = []
    total = 0
    for seed in FROZEN_SEEDS:
        rng = random.Random(seed)
        for i in range(SCENARIOS_PER_SEED):
            sid = seed * 1_000_000 + i
            out = _run_scenario(rng, sid)
            assert out["ok"] is True
            results.append(out)
            total += 1
    assert total >= TOTAL_TARGET
    assert total == 10_000
    # at least some fills and some rejects across corpus
    branches = {r["branch"] for r in results}
    assert len(branches) >= 2
    # exchange write always 0 across sample reports
    for r in results[::500]:
        if "report" in r:
            assert r["report"]["exchange_write_attempt_count"] == 0


def test_ceiling_leverage_constant():
    assert MAX_LEVERAGE_CEILING == 50
    sim = _immutable_sim(leverage=50)
    assert sim.leverage == 50
