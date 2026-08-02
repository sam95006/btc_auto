"""Edge Research V2 unit tests."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_demo_execution.edge_research_v2_hypotheses import HYPOTHESES_V2, TIMEFRAME_JUSTIFICATION
from backend.nexus_demo_execution.edge_research_v2 import _edge_from_costs, _promote
from backend.nexus_demo_execution.session_limits import MIN_NET_REWARD_RISK_RATIO, MIN_NET_REWARD_TO_COST
from backend.nexus_demo_execution.oos_risk_audit import CONSUMED_STATUS


def test_nine_hypotheses_pre_registered():
    assert len(HYPOTHESES_V2) == 9
    assert all(h["created_before_evaluation"] is True for h in HYPOTHESES_V2)
    families = {h["family"] for h in HYPOTHESES_V2}
    assert families == {"H1", "H2", "H3"}


def test_timeframe_justification_holding_driven():
    assert TIMEFRAME_JUSTIFICATION["strategy_tf"] == "15"
    assert "holding" in TIMEFRAME_JUSTIFICATION["reason"].lower() or "hold" in TIMEFRAME_JUSTIFICATION["reason"].lower()


def test_floors_unchanged():
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert MIN_NET_REWARD_TO_COST == 1.5


def test_consumed_oos_frozen():
    assert CONSUMED_STATUS == "CONSUMED_FAILED_HOLDOUT"


def test_marginal_gross_not_edge():
    edge = _edge_from_costs(
        {"completed_trade_count": 30, "gross_profit_factor": 1.02, "gross_expectancy": 0.01},
        {"completed_trade_count": 30, "net_profit_factor": 0.8},
        {"completed_trade_count": 30, "net_profit_factor": 0.7},
    )
    assert edge == "NO_GROSS_EDGE"


def test_promote_requires_sample_and_symbols():
    status = _promote(
        {
            "base": {
                "completed_trade_count": 40,
                "net_expectancy": 0.2,
                "net_profit_factor": 1.2,
                "maximum_drawdown": -5,
                "symbols": ["BTCUSDT"],
            },
            "adverse": {"net_profit_factor": 1.0},
            "gross": {"gross_expectancy": 0.3},
            "fold_positive_count": 3,
            "fold_usable_count": 3,
        }
    )
    assert status == "REJECTED"  # single-symbol dependency


def test_mainnet_forbidden():
    from backend.nexus_demo_execution import MAINNET, REAL_MONEY

    assert MAINNET is False
    assert REAL_MONEY is False


def test_secret_scan():
    for rel in (
        "backend/nexus_demo_execution/edge_research_v2.py",
        "backend/nexus_demo_execution/edge_research_v2_hypotheses.py",
    ):
        text = Path(rel).read_text(encoding="utf-8")
        assert "api.bybit.com" not in text
        for needle in ("API_KEY", "api_secret", "SECRET_KEY=", "BEGIN PRIVATE"):
            assert needle not in text
