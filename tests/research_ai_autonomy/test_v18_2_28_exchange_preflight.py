# -*- coding: utf-8 -*-
"""V18.2.28 — exchange preflight + qty normalization + fall-through."""
from backend.nexus_research_ai_autonomy.exchange_preflight import (
    EXCHANGE_SIZE_INFEASIBLE,
    normalize_qty,
    preflight_ranked_candidates,
    run_exchange_preflight,
)
from backend.nexus_research_ai_autonomy.market_opportunity_selection import MarketCandidate


class _FakeClient:
    def fetch_instrument(self, symbol: str):
        return {
            "symbol": symbol,
            "status": "Trading",
            "lotSizeFilter": {
                "qtyStep": "0.001",
                "minOrderQty": "0.001",
                "minNotionalValue": "5",
                "maxOrderQty": "1000000",
            },
            "priceFilter": {"tickSize": "0.01"},
        }

    def qty_step(self, info):
        return 0.001

    def min_qty(self, info):
        return 0.001

    def min_notional(self, info):
        return 5.0

    def tick_size(self, info):
        return 0.01


def test_normalize_qty_step():
    s, f = normalize_qty(1.23456, qty_step=0.001)
    assert f == 1.234
    assert s == "1.234"


def test_exchange_preflight_pass():
    pf = run_exchange_preflight(
        client=_FakeClient(),  # type: ignore[arg-type]
        symbol="BTCUSDT",
        entry_price=64000.0,
        equity=5000.0,
    )
    assert pf["preflight_pass"] is True
    assert pf.get("normalized_qty")


def test_preflight_fallthrough_skips_infeasible():
    good = MarketCandidate(
        symbol="GOODUSDT",
        strategy_family="TREND",
        direction="LONG",
        entry_price=64000.0,
        economic_edge_pass=True,
        horizon_feasibility_pass=True,
        horizon_config_valid=True,
        risk_pass=True,
        rank_score=2.0,
    )
    bad = MarketCandidate(
        symbol="BADUSDT",
        strategy_family="TREND",
        direction="LONG",
        entry_price=0.0001,
        economic_edge_pass=True,
        horizon_feasibility_pass=True,
        horizon_config_valid=True,
        risk_pass=False,
        rank_score=3.0,
    )
    out = preflight_ranked_candidates(
        [bad, good],
        client=_FakeClient(),  # type: ignore[arg-type]
        equity=5000.0,
    )
    assert out["fallthrough_enabled"] is True
    assert out["cycle_terminated_on_first_failure"] is False
    assert out["action"] == "SELECT"
    assert out["selected"]["symbol"] == "GOODUSDT"


def test_exchange_size_infeasible_constant():
    assert EXCHANGE_SIZE_INFEASIBLE == "EXCHANGE_SIZE_INFEASIBLE"
