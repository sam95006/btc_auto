"""Tests for V16-D Strategy Expert Router."""
from __future__ import annotations

import pytest

from backend.nexus_strategy_expert_router.champion_challenger import (
    RouterPolicySnapshot,
    RouterPromotionGate,
    default_challenger,
    default_champion,
)
from backend.nexus_strategy_expert_router.constants import (
    DEFENSIVE_EXPERT,
    DECISION_SIDES,
    EXPERT_IDS,
    FIXED_LEVERAGE,
    HARD_BANS,
    NO_TRADE_SIDES,
    ROUTING_FACTORS,
)
from backend.nexus_strategy_expert_router.cooldown import CooldownBook
from backend.nexus_strategy_expert_router.experts import assert_expert_catalog_complete
from backend.nexus_strategy_expert_router.fixtures import (
    all_fixtures,
    fixture_defensive_stress,
    fixture_lesson_forced_abstain,
    fixture_low_trust,
    fixture_mean_reversion_crowding,
    fixture_risk_gate_blocked,
    fixture_strong_trend_long,
)
from backend.nexus_strategy_expert_router.formal_params import (
    FormalParamLock,
    FormalRouterParams,
)
from backend.nexus_strategy_expert_router.hard_bans import (
    HardBanViolation,
    assert_no_status_json_filenames,
    hard_ban_inventory,
    hard_ban_probe_matrix,
    refuse_ai_override_risk_gate,
    refuse_ai_set_leverage,
    refuse_status_json_lane_artifact,
)
from backend.nexus_strategy_expert_router.harness import run_strategy_expert_router_campaign
from backend.nexus_strategy_expert_router.router import StrategyExpertRouter
from backend.nexus_strategy_expert_router.safety_gates import (
    SafetyGateRejected,
    apply_ai_safety_suggestion,
    assert_safety_invariants,
    honor_risk_gate,
    resolve_leverage,
)
from backend.nexus_strategy_expert_router.scoring import score_all_experts
from backend.nexus_strategy_expert_router.three_pass import run_three_passes


def test_expert_catalog_complete() -> None:
    assert_expert_catalog_complete()
    assert len(EXPERT_IDS) == 10
    assert DEFENSIVE_EXPERT in EXPERT_IDS


def test_hard_bans_enforced() -> None:
    inv = hard_ban_inventory()
    assert inv["enforced"] is True
    assert set(HARD_BANS) == set(inv["hard_bans"])
    matrix = hard_ban_probe_matrix()
    assert matrix["all_raised"] is True
    with pytest.raises(HardBanViolation):
        refuse_ai_set_leverage()
    with pytest.raises(HardBanViolation):
        refuse_ai_override_risk_gate()
    with pytest.raises(HardBanViolation):
        refuse_status_json_lane_artifact()
    with pytest.raises(HardBanViolation):
        assert_no_status_json_filenames(["artifacts/lane_status.json"])


def test_routing_factors_present_on_scores() -> None:
    scores = score_all_experts(fixture_strong_trend_long())
    assert len(scores) == 10
    for s in scores:
        assert set(s.factor_breakdown) == set(ROUTING_FACTORS)


def test_strong_trend_prefers_directional_expert() -> None:
    d = StrategyExpertRouter().route(fixture_strong_trend_long())
    assert d.side in DECISION_SIDES
    assert d.expert_id in EXPERT_IDS
    assert d.leverage == FIXED_LEVERAGE
    assert d.reason_trace.steps
    assert d.reason_trace.to_dict()["step_count"] >= 4
    # Healthy trend should not be forced into defensive-only.
    assert d.expert_id != DEFENSIVE_EXPERT or d.no_trade


def test_defensive_can_win_under_stress() -> None:
    d = StrategyExpertRouter().route(fixture_defensive_stress())
    assert d.no_trade is True
    assert d.side in NO_TRADE_SIDES
    assert d.expert_id == DEFENSIVE_EXPERT


def test_low_trust_no_trade() -> None:
    d = StrategyExpertRouter().route(fixture_low_trust())
    assert d.no_trade is True
    assert d.side in NO_TRADE_SIDES


def test_mean_reversion_fixture_routes() -> None:
    d = StrategyExpertRouter().route(fixture_mean_reversion_crowding())
    assert d.side in DECISION_SIDES
    assert d.leverage == FIXED_LEVERAGE
    assert any(s.expert_id == "MEAN_REVERSION" for s in d.expert_scores)


def test_risk_gate_honored_ai_cannot_override() -> None:
    d = StrategyExpertRouter().route(
        fixture_risk_gate_blocked(),
        ai_override_risk_gate={
            "override_risk_gate": True,
            "force_allow": True,
            "risk_gate_allow": True,
        },
        ai_attempt_set_leverage=True,
    )
    assert d.risk_gate_honored is True
    assert d.ai_override_risk_gate_applied is False
    assert d.ai_set_leverage_applied is False
    assert d.leverage == FIXED_LEVERAGE
    assert d.side in NO_TRADE_SIDES
    assert d.no_trade is True


def test_lesson_restrictions_block_experts() -> None:
    d = StrategyExpertRouter().route(fixture_lesson_forced_abstain())
    blocked = {
        s.expert_id
        for s in d.expert_scores
        if "lesson_restriction" in s.block_reasons
    }
    assert "TREND" in blocked
    assert "BREAKOUT" in blocked
    assert d.no_trade is True or d.expert_id == DEFENSIVE_EXPERT


def test_ai_safety_suggestion_rejected() -> None:
    d = StrategyExpertRouter().route(fixture_strong_trend_long()).to_dict()
    out = apply_ai_safety_suggestion(
        d,
        {"leverage": 100, "risk_gate_allow": True, "side": "SHORT", "override_risk_gate": True},
    )
    assert out["leverage"] == FIXED_LEVERAGE
    assert out["ai_set_leverage_applied"] is False
    assert out["ai_override_risk_gate_applied"] is False
    assert_safety_invariants(out)
    with pytest.raises(SafetyGateRejected):
        assert_safety_invariants({**out, "ai_set_leverage_applied": True})


def test_resolve_leverage_and_risk_gate_helpers() -> None:
    lev = resolve_leverage(requested_leverage=100, ai_attempt_set_leverage=True)
    assert lev["leverage"] == FIXED_LEVERAGE
    assert lev["ai_set_leverage_applied"] is False
    gate = honor_risk_gate(
        risk_gate_allow=False,
        risk_gate_reason="KILL_SWITCH",
        ai_override_attempt={"force_allow": True},
    )
    assert gate["effective_allow"] is False
    assert gate["ai_override_risk_gate_applied"] is False


def test_formal_param_anti_thrash() -> None:
    lock = FormalParamLock()
    ok = lock.propose_update(FormalRouterParams(min_data_trust=0.5), ts_ms=1_000_000)
    assert ok["accepted"] is True
    with pytest.raises(HardBanViolation, match="no_per_minute_formal_param_thrash"):
        lock.propose_update(FormalRouterParams(min_data_trust=0.55), ts_ms=1_030_000)
    # After dwell, accept.
    later = lock.propose_update(
        FormalRouterParams(min_data_trust=0.55),
        ts_ms=1_000_000 + 15 * 60 * 1000,
    )
    assert later["accepted"] is True


def test_cooldown_and_degradation() -> None:
    book = CooldownBook()
    router = StrategyExpertRouter(cooldown=book)
    ctx = fixture_strong_trend_long()
    first = router.route(ctx)
    second = router.route(ctx)
    if first.expert_id != DEFENSIVE_EXPERT:
        cooled = any(
            "cooldown_active" in s.block_reasons
            for s in second.expert_scores
            if s.expert_id == first.expert_id
        )
        assert cooled or second.expert_id != first.expert_id
    for _ in range(3):
        book.record_soft_failure("BREAKOUT")
    assert book.is_degraded("BREAKOUT") is True
    # Defensive never cools out.
    book.record_selection(DEFENSIVE_EXPERT, ctx.ts_ms)
    assert book.is_cooling(DEFENSIVE_EXPERT, ctx.ts_ms) is False


def test_champion_challenger_shadow_only() -> None:
    gate = RouterPromotionGate()
    champ = default_champion()
    chall = default_challenger()
    early = gate.evaluate(champ, chall)
    assert early.promoted is False
    assert early.reason == "insufficient_sample"
    live = gate.evaluate(champ, chall, requested_status="LIVE_APPLIED")
    assert live.promoted is False
    assert live.reason == "live_promotion_forbidden"
    ready = RouterPolicySnapshot(
        policy_id="ready",
        role="SHADOW_CHALLENGER",
        sample_size=40,
        no_trade_win_rate=0.70,
        entry_regret=0.20,
        status="SHADOW_ONLY",
    )
    ok = gate.evaluate(champ, ready)
    assert ok.promoted is True
    assert ok.to_dict()["live_applied"] is False
    assert ok.to_dict()["auto_promoted"] is False


def test_all_fixtures_produce_reason_traces() -> None:
    router = StrategyExpertRouter()
    for fid, ctx in all_fixtures().items():
        d = router.route(ctx)
        assert d.side in DECISION_SIDES, fid
        assert d.reason_trace.to_dict()["step_count"] >= 3, fid
        assert d.leverage == FIXED_LEVERAGE, fid
        assert d.challenger_expert_id is None or d.challenger_expert_id in EXPERT_IDS


def test_campaign_three_passes_pass() -> None:
    report = run_strategy_expert_router_campaign(pass_id=1)
    assert report["status_json_written"] is False
    assert report["status_report_written"] is False
    assert report["exchange_write_attempt_count"] == 0
    assert report["formal_walk_forward_executed"] is False
    assert report["oos_consumed"] is False
    assert set(HARD_BANS).issubset(set(report["hard_bans"]))
    assert report["three_pass"]["all_pass"] is True
    assert report["pass"] is True
    assert report["status"] == "PASS"
    assert report["decision_count"] == len(all_fixtures())
    assert report["degradation_active_breakout"] is True
    # No-trade first-class in campaign outputs.
    sides = {d["side"] for d in report["decisions"]}
    assert sides & NO_TRADE_SIDES


def test_three_pass_detects_status_artifact_claim() -> None:
    report = run_strategy_expert_router_campaign(pass_id=2)
    poisoned = dict(report)
    poisoned["status_json_written"] = True
    three = run_three_passes(poisoned)
    assert three["all_pass"] is False
    ids = {f["id"] for p in three["passes"] for f in p["findings"]}
    assert "P3_STATUS_ARTIFACT" in ids


def test_defensive_never_emits_entry_side() -> None:
    d = StrategyExpertRouter().route(fixture_defensive_stress())
    assert d.expert_id == DEFENSIVE_EXPERT
    assert d.side not in ("LONG", "SHORT")
