"""6H V2 readiness unit tests — no exchange write."""
from __future__ import annotations

import os

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["DEMO_AUTONOMOUS_ENABLED"] = "false"
os.environ["DEMO_6H_V2_DRY_RUN_ONLY"] = "true"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_demo_execution.fee_rate import configured_conservative_quote
from backend.nexus_demo_execution.session_limits import MIN_NET_REWARD_RISK_RATIO
from backend.nexus_demo_execution.trade_geometry import compute_structure_geometry
from backend.nexus_demo_execution.v2_decision_delta import (
    build_learning_delta,
    classify_block_event,
    is_learning_decision_delta,
)
from backend.nexus_demo_execution.v2_evidence_schema import contains_forbidden_secrets, evidence_manifest
from backend.nexus_demo_execution.v2_policy import MIN_NET_REWARD_RISK_RATIO as V2_RR
from backend.nexus_demo_execution.v2_session_controller import SessionControllerV2
from backend.nexus_demo_execution.v2_six_role import evaluate_six_role_review, stub_complete_roles


def _cand(**kw):
    base = {
        "candidate_id": "c1",
        "symbol": "ETHUSDT",
        "side": "Buy",
        "entry_reference": 100.0,
        "atr": 2.5,
        "recent_swing_high": 112.0,
        "recent_swing_low": 94.0,
        "support_levels": [93.0],
        "resistance_levels": [115.0],
        "liquidity_above": [114.0],
        "liquidity_below": [92.0],
        "spread_bps": 1.0,
        "slippage_bps": 1.0,
        "funding_rate": 0.0001,
        "tick_size": 0.01,
    }
    base.update(kw)
    return base


def test_net_rr_unchanged():
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert V2_RR == 1.2


def test_geometry_missing_blocks():
    g = compute_structure_geometry(
        side="Buy",
        entry_price=100,
        atr=None,
        recent_swing_high=110,
        recent_swing_low=90,
        support=89,
        resistance=111,
        fee_rate=0.00055,
    )
    assert g.allowed is False
    assert g.block_reason == "GEOMETRY_INPUT_MISSING"


def test_structure_geometry_long_short():
    long = compute_structure_geometry(
        side="Buy",
        entry_price=100,
        atr=3,
        recent_swing_high=120,
        recent_swing_low=90,
        support=88,
        resistance=125,
        fee_rate=0.00055,
        qty=5,
        spread_bps=1,
        slippage_bps=1,
    )
    short = compute_structure_geometry(
        side="Sell",
        entry_price=100,
        atr=3,
        recent_swing_high=110,
        recent_swing_low=80,
        support=75,
        resistance=112,
        fee_rate=0.00055,
        qty=5,
        spread_bps=1,
        slippage_bps=1,
    )
    assert long.allowed or long.block_reason.startswith("BLOCK_")
    assert short.allowed or short.block_reason.startswith("BLOCK_")
    assert long.geometry_source == "STRUCTURE"
    assert short.geometry_source == "STRUCTURE"


def test_decision_delta_not_cost_block():
    ev = classify_block_event("BLOCK_COST_DOMINATED_ENTRY")
    assert ev["decision_delta"] is False
    assert is_learning_decision_delta({"reason": "FEE_RATE_UNKNOWN"}) is False
    d = build_learning_delta(
        source_trade_case_id="tc",
        reflection_id="r",
        similar_candidate_id="c",
        similarity_score=0.9,
        before_verdict="ALLOW",
        after_verdict="BLOCK",
        before_score=1.0,
        after_score=0.2,
        guard_action="EXACT_SETUP_COOLDOWN",
        policy_version="v2",
    )
    assert is_learning_decision_delta(d) is True


def test_six_role_and_risk_veto():
    incomplete = evaluate_six_role_review({"market_context": {"verdict": "ALLOW"}})
    assert incomplete["reason"] == "ROLE_REVIEW_INCOMPLETE"
    veto = evaluate_six_role_review(stub_complete_roles(risk_verdict="VETO"))
    assert veto["reason"] == "RISK_CRITIC_VETO"
    ok = evaluate_six_role_review(stub_complete_roles())
    assert ok["allowed"] is True


def test_session_controller_dry_run_no_write():
    ctl = SessionControllerV2()
    r = ctl.evaluate_candidate(_cand(), roles=stub_complete_roles())
    assert r["allowed"] is True
    assert ctl.exchange_write_call_count == 0
    assert ctl.summary()["mainnet"] is False
    assert ctl.summary()["real_money"] is False


def test_session_blocks_stale_and_duplicate():
    ctl = SessionControllerV2()
    roles = stub_complete_roles()
    assert ctl.evaluate_candidate(_cand(), roles=roles, duplicate_intent=True)["allowed"] is False
    assert (
        ctl.evaluate_candidate(
            _cand(),
            roles=roles,
            account={
                "snapshot_age_sec": 99,
                "position_count": 0,
                "open_order_count": 0,
                "available_balance": 100,
                "reconciliation": "MATCH",
                "execution_owner_count": 1,
            },
        )["allowed"]
        is False
    )


def test_evidence_schema_no_secrets():
    m = evidence_manifest(session_id="s", policy_version="p", dry_run=True)
    assert "orders.jsonl" in m["files"]
    assert contains_forbidden_secrets({"api_key": "x"}) 
    assert not contains_forbidden_secrets({"symbol": "BTCUSDT"})


def test_fee_conservative_env(monkeypatch):
    monkeypatch.setenv("NEXUS_FEE_RATE_CONSERVATIVE_ENABLED", "true")
    monkeypatch.setenv("NEXUS_FEE_RATE_CONSERVATIVE_FOUNDER_APPROVED", "true")
    monkeypatch.setenv("NEXUS_FEE_RATE_CONSERVATIVE_TAKER", "0.00055")
    monkeypatch.setenv("NEXUS_FEE_RATE_CONSERVATIVE_MAKER", "0.00020")
    monkeypatch.setenv("NEXUS_FEE_RATE_VERSION", "founder-conservative-v1-2026-07-31")
    monkeypatch.setenv("NEXUS_FEE_RATE_REVIEW_BY", "2026-08-31")
    q = configured_conservative_quote(symbol="BTCUSDT")
    assert q is not None
    assert q.status == "FEE_RATE_CONFIGURED_CONSERVATIVE"
    assert abs(float(q.pretrade_round_trip_fee_rate or 0) - 0.0011) < 1e-9
