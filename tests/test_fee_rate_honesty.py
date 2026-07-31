"""Unit tests for honest fee-rate resolution and cost-gate UNAVAILABLE semantics."""
from __future__ import annotations

import os

import pytest

from backend.nexus_demo_execution.cost_entry_gate import evaluate_cost_gate
from backend.nexus_demo_execution.fee_rate import (
    FEE_RATE_CONFIGURED_CONSERVATIVE,
    FEE_RATE_LIVE,
    FEE_RATE_UNAVAILABLE,
    clear_fee_cache,
    configured_conservative_quote,
    parse_fee_rows,
)


@pytest.fixture(autouse=True)
def _clear():
    clear_fee_cache()
    for k in list(os.environ):
        if k.startswith("NEXUS_FEE_RATE_CONSERVATIVE"):
            os.environ.pop(k, None)
    yield
    clear_fee_cache()


def test_parse_fee_rows_live():
    q = parse_fee_rows([{"makerFeeRate": "0.0002", "takerFeeRate": "0.00055"}], "BTCUSDT")
    assert q.status == FEE_RATE_LIVE
    assert q.usable_taker == pytest.approx(0.00055)
    assert q.new_entry_blocked is False


def test_parse_fee_rows_empty_is_unavailable():
    q = parse_fee_rows([], "ETHUSDT")
    assert q.status != FEE_RATE_LIVE
    assert q.usable_taker is None
    assert q.fail_closed is True


def test_conservative_requires_founder_flags():
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_ENABLED"] = "true"
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_TAKER"] = "0.00055"
    assert configured_conservative_quote("BTCUSDT") is None
    os.environ["NEXUS_FEE_RATE_CONSERVATIVE_FOUNDER_APPROVED"] = "true"
    q = configured_conservative_quote("BTCUSDT")
    assert q is not None
    assert q.status == FEE_RATE_CONFIGURED_CONSERVATIVE
    assert q.usable_taker == pytest.approx(0.00055)


def test_cost_gate_unavailable_does_not_emit_zero_costs():
    r = evaluate_cost_gate(
        entry_price=100.0,
        stop_loss=99.0,
        take_profit=101.0,
        qty=5.0,
        side="Buy",
        fee_rate=None,
        funding_rate=0.0001,
        slippage_bps=1.0,
        fee_meta={"status": FEE_RATE_UNAVAILABLE, "fee_source": "test", "fee_fetch_error": "empty"},
    )
    assert r.allowed is False
    assert r.reason == "FEE_RATE_UNKNOWN"
    assert r.estimated_net_reward == "UNAVAILABLE"
    assert r.estimated_total_cost == "UNAVAILABLE"
    assert r.breakdown["estimated_entry_fee"] == "UNAVAILABLE"
    assert r.breakdown["fee_fetch_error"] == "empty"


def test_cost_gate_pass_with_live_fee():
    r = evaluate_cost_gate(
        entry_price=100.0,
        stop_loss=99.2,
        take_profit=100.8,
        qty=5.0,
        side="Buy",
        fee_rate=0.00055,
        funding_rate=0.0001,
        slippage_bps=1.0,
        fee_meta={"status": FEE_RATE_LIVE, "fee_source": "test", "taker_fee_rate": 0.00055},
    )
    assert r.fee_rate_status == FEE_RATE_LIVE
    assert isinstance(r.estimated_total_cost, float)
    assert r.breakdown["notional"] == pytest.approx(500.0)
