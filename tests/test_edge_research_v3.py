"""Edge Research V3 unit tests."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_demo_execution.edge_research_v3_hypotheses import (
    HYPOTHESES_V3,
    RESEARCH_WAVE_V2_STATUS,
)
from backend.nexus_demo_execution.session_limits import MIN_NET_REWARD_RISK_RATIO, MIN_NET_REWARD_TO_COST
from backend.nexus_demo_execution.oos_risk_audit import CONSUMED_STATUS


def test_v2_wave_frozen():
    assert RESEARCH_WAVE_V2_STATUS == "CONSUMED_NO_VALIDATED_COHORT"


def test_v3_hypotheses_pre_registered_unique_ids():
    ids = [h["hypothesis_id"] for h in HYPOTHESES_V3]
    assert len(ids) == len(set(ids))
    assert all(h["created_before_evaluation"] is True for h in HYPOTHESES_V3)
    # no reused V2 IDs
    assert all(not hid.startswith("H1A_") and "H2A_" not in hid for hid in ids)


def test_floors_unchanged():
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert MIN_NET_REWARD_TO_COST == 1.5


def test_consumed_oos_still_frozen():
    assert CONSUMED_STATUS == "CONSUMED_FAILED_HOLDOUT"


def test_economic_prefilter_ratio():
    from backend.nexus_demo_execution.edge_research_v3 import _economic_prefilter

    ok, meta = _economic_prefilter(entry=100.0, target=97.0, stop=100.5, min_move_to_cost=2.0)
    assert "gross_move_to_cost_ratio" in meta
    assert meta["expected_gross_move_usdt"] > 0


def test_lookup_asof_none_not_zero():
    from backend.nexus_demo_execution.microstructure_history import lookup_asof

    assert lookup_asof([], 1, "funding_rate") is None
    assert lookup_asof([{"ts_ms": 10, "funding_rate": 0.0001}], 5, "funding_rate") is None


def test_mainnet_forbidden():
    from backend.nexus_demo_execution import MAINNET, REAL_MONEY

    assert MAINNET is False
    assert REAL_MONEY is False


def test_secret_scan_v3():
    for rel in (
        "backend/nexus_demo_execution/edge_research_v3.py",
        "backend/nexus_demo_execution/microstructure_history.py",
        "backend/nexus_demo_execution/edge_research_v3_hypotheses.py",
    ):
        text = Path(rel).read_text(encoding="utf-8")
        assert "api.bybit.com" not in text
        for needle in ("API_KEY", "api_secret", "SECRET_KEY=", "BEGIN PRIVATE"):
            assert needle not in text
