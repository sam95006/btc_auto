"""Focused tests for V18.2.17 Research AI Autonomy."""
from __future__ import annotations

import time

from backend.nexus_research_ai_autonomy.ai_roles import HOT_PATH_GUARD, ResearchReasoner
from backend.nexus_research_ai_autonomy.autonomy_runtime import ResearchAutonomyRuntime
from backend.nexus_research_ai_autonomy.constants import IMPLEMENTED_STRATEGY_FAMILIES
from backend.nexus_research_ai_autonomy.exploration_gate import ResearchExplorationGateV1
from backend.nexus_research_ai_autonomy.fast_path import FastPathExecutor, SimulatedDemoTransport
from backend.nexus_research_ai_autonomy.market_state import MarketStateEngine
from backend.nexus_research_ai_autonomy.policies import formal_gate_blocks_research
from backend.nexus_research_ai_autonomy.prepared_decision import PreparedDecision
from backend.nexus_research_ai_autonomy.radar_feed import ServerRadarFeed
from backend.nexus_research_ai_autonomy.strategy_router import ResearchStrategyRouter


def _radar_snapshot():
    return {
        "ranking_authority": "SERVER",
        "candidates": [
            {"symbol": "SUIUSDT", "rank": 1, "score": 92.0, "radar_eligible": True, "trade_eligible": False},
            {"symbol": "ETHUSDT", "rank": 2, "score": 80.0, "radar_eligible": True, "trade_eligible": False},
            {"symbol": "ARBUSDT", "rank": 3, "score": 70.0, "radar_eligible": True, "trade_eligible": False},
        ],
    }


def test_nine_families_mapped_no_invention():
    router = ResearchStrategyRouter()
    assert set(router.families()) == set(IMPLEMENTED_STRATEGY_FAMILIES)
    assert len(router.families()) == 9
    r = router.route("LIQUIDITY_STRESS")
    assert r.selected_strategy_family is None
    assert r.abstain_reason


def test_uncertain_regime_valid():
    ms = MarketStateEngine().evaluate({"freshness_sec": 5, "data_trust": 0.9})
    assert ms.regime_primary == "UNCERTAIN"


def test_formal_wf_does_not_block_research():
    assert formal_gate_blocks_research({"pre_wf": 0, "formal_wf": "NOT_RUN", "oos": "NOT_RUN"}) is False


def test_exploration_gate_allows_radar_without_trade_eligible():
    gate = ResearchExplorationGateV1().evaluate(
        {
            "data_trust": 0.9,
            "freshness_sec": 5,
            "exchange_ok": True,
            "position_safety_ok": True,
            "loss_safety_ok": True,
            "regime": "TREND_UP",
            "strategy_fit_score": 0.85,
            "expected_edge": 0.01,
            "estimated_cost": 0.001,
            "spread": 0.0004,
            "liquidity": 0.8,
            "ai_quant_agreement": True,
            "critic_objections": [],
            "radar_eligible": True,
            "trade_eligible": False,
        }
    )
    assert gate.passed
    assert "radar_eligible_without_trade_eligible_allowed" in gate.reasons


def test_browser_radar_rejected():
    feed = ServerRadarFeed()
    try:
        feed.ingest_snapshot({"ranking_authority": "BROWSER", "candidates": []})
        assert False, "expected reject"
    except ValueError as exc:
        assert "browser_ranking_rejected" in str(exc)


def test_prepared_decision_states_and_ttl():
    pd = PreparedDecision(symbol="SUIUSDT", side="LONG", status="PREPARING")
    pd.transition("READY", reason="ok")
    pd.expires_at = int(time.time() * 1000) - 1
    reason = pd.check_invalidate()
    assert reason == "ttl"
    assert pd.status == "EXPIRED"


def test_fast_path_no_ai_leak_and_latency():
    HOT_PATH_GUARD.slow_path_leak_count = 0
    HOT_PATH_GUARD.leaks.clear()
    transport = SimulatedDemoTransport(send_delay_ms=1, ack_delay_ms=1, fill_delay_ms=1)
    fp = FastPathExecutor(transport=transport)
    pd = PreparedDecision(
        symbol="SUIUSDT",
        side="LONG",
        regime="TREND_UP",
        strategy_family="TREND",
        entry_trigger={"type": "price_cross", "price": 1.0, "side": "LONG"},
        entry_zone={"mid": 1.0, "width_pct": 0.001},
        stop_logic={"type": "protective_stop", "price": 0.95},
        max_hold=600,
        requested_size=0.001,
        status="PREPARING",
    )
    pd.transition("READY", reason="test")
    res = fp.execute_if_triggered(pd, market_update={"last_price": 1.01, "event_ts": int(time.time() * 1000)})
    assert res["executed"] is True
    assert res["slow_path_leak"] is False
    assert res["execution_purpose"] == "RESEARCH_AI_DEMO"
    assert res["latency"]["deltas_ms"]["trigger_to_send_ms"] is not None


def test_fast_path_flags_ai_leak():
    HOT_PATH_GUARD.slow_path_leak_count = 0
    HOT_PATH_GUARD.leaks.clear()
    fp = FastPathExecutor(transport=SimulatedDemoTransport(send_delay_ms=0, ack_delay_ms=0, fill_delay_ms=0))
    pd = PreparedDecision(
        symbol="SUIUSDT",
        side="LONG",
        entry_trigger={"price": 1.0},
        stop_logic={"price": 0.9},
        max_hold=100,
        requested_size=0.001,
        status="PREPARING",
    )
    pd.transition("READY", reason="t")

    def leaky():
        ResearchReasoner().reason(
            symbol="SUIUSDT",
            regime="TREND_UP",
            family="TREND",
            quant=__import__("backend.nexus_research_ai_autonomy.ai_roles", fromlist=["QuantResult"]).QuantResult(
                symbol="SUIUSDT",
                score=80,
                expected_move=0.01,
                expected_edge=0.008,
                estimated_cost=0.001,
                side_bias="LONG",
            ),
        )

    res = fp.execute_if_triggered(
        pd,
        market_update={"last_price": 1.1, "event_ts": int(time.time() * 1000)},
        ai_callable_probe=leaky,
    )
    assert res["executed"] is True
    assert res["slow_path_leak"] is True or HOT_PATH_GUARD.slow_path_leak_count > 0


def test_end_to_end_research_lifecycle_and_funnel():
    rt = ResearchAutonomyRuntime()
    rt.fast_path.transport = SimulatedDemoTransport(send_delay_ms=1, ack_delay_ms=1, fill_delay_ms=1)
    market_inputs = {
        "trend": 0.7,
        "momentum": 0.55,
        "volatility": 0.4,
        "data_trust": 0.95,
        "freshness_sec": 3,
        "spread": 0.0003,
        "liquidity": 0.9,
        "funding": 0.00005,
        "volume": 1.0,
        "activity": 0.8,
        "cost_estimate": 0.0005,
    }
    features = {
        "SUIUSDT": {
            "momentum": 0.6,
            "volatility": 0.4,
            "last_price": 1.0,
            "price": 1.0,
            "atr_pct": 0.01,
            "spread": 0.0003,
            "liquidity": 0.9,
            "funding": 0.00005,
            "data_trust": 0.95,
            "freshness_sec": 3,
            "min_size": 0.001,
        }
    }
    slow = rt.run_slow_path_cycle(
        market_inputs=market_inputs,
        radar_snapshot=_radar_snapshot(),
        symbol_features=features,
        formal_status={"pre_wf": 0, "formal_wf": "NOT_RUN"},
    )
    assert slow["formal_gates_not_blocking"] is True
    assert rt.metrics.prepared_decisions_created >= 1
    ready = rt.decisions.list_by_status("READY")
    assert ready
    pd = ready[0]
    # Force trigger hit
    trig = float((pd.entry_trigger or {}).get("price") or 1.0)
    fast = rt.run_fast_path_for_ready({pd.symbol: {"last_price": trig + 0.01, "price": trig + 0.01, "event_ts": int(time.time() * 1000)}})
    assert any(x.get("executed") for x in fast)
    assert rt.metrics.slow_path_leak_count == 0
    open_id = [p for p in rt.positions.positions.values() if p.status == "OPEN"][0].position_id
    # Exit via max hold by manipulating opened_at
    pos = rt.positions.positions[open_id]
    pos.opened_at_ms = int(time.time() * 1000) - (pos.max_hold_sec + 10) * 1000
    managed = rt.manage_open_positions({pos.symbol: {"last_price": trig + 0.02, "price": trig + 0.02, "liquidity": 0.9}})
    assert managed and managed[0]["action"] == "EXIT"
    refs = rt.run_reflection_async()
    assert refs
    assert rt.metrics.active_lessons_created_from_live_demo == 0
    funnel = rt.metrics.funnel_counts()
    assert funnel["orders_executed"] >= 1
    assert funnel["radar_candidates"] >= 1
    mon = rt.monitor_snapshot()
    assert mon["founder_only"] is True
    assert mon["member_product"] is False
    assert "api_key" not in str(mon).lower()


def test_wait_horizon_evaluation():
    rt = ResearchAutonomyRuntime()
    ev = rt.reflection.evaluate_non_trade_horizon(
        decision_id="d1",
        verdict="WAIT",
        market_move_pct=3.0,
        ai_wanted_side="LONG",
    )
    assert ev.classification in {"bad_avoided_trade", "correct_wait_or_uncertain", "uncertain"}


def test_lesson_firewall_blocks_active_from_live_demo():
    rt = ResearchAutonomyRuntime()
    out = rt.lessons.ingest_lesson_candidate(
        {
            "status": "LESSON_CANDIDATE",
            "error_class": "TIMING_ERROR",
            "summary": "test",
        }
    )
    assert out["accepted"] is True
    assert rt.lessons.active_lessons_created_from_live_demo == 0
