"""Dynamic universe + AI learning + H5 portability research V1 tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

ROOT = Path(__file__).resolve().parents[1]

from backend.nexus_ai_gateway import (
    AIGateway,
    MockProvider,
    redact_for_external,
    validate_against_schema,
)
from backend.nexus_demo_execution.closed_historical_registry import assert_september_partial_excluded
from backend.nexus_demo_execution.edge_research_h5 import (
    classify_h5,
    chronological_folds,
    preregistration_checksum,
    preregistration_payload,
    sha_obj,
)
from backend.nexus_demo_execution.edge_research_h5_hypotheses import H5_GATES, HYPOTHESES_H5
from backend.nexus_dynamic_universe import (
    UNIVERSE_ID,
    normalize_instrument,
    point_in_time_membership,
)
from backend.nexus_dynamic_universe.historical_acquisition import eligibility_gates
from backend.nexus_dynamic_universe.symbol_profile import classify_meme
from backend.nexus_learning import (
    FORBIDDEN_IMMEDIATE,
    LessonMemory,
    create_lesson_from_outcome,
    deterministic_risk_critic,
    main_reasoner_with_lessons,
    qualification_identity,
)


def test_universe_id_single_no_fleet():
    assert UNIVERSE_ID == "NEXUS_DYNAMIC_LINEAR_USDT_UNIVERSE"
    snap = {
        "instruments": [
            {
                "symbol": "BTCUSDT",
                "eligible": True,
                "launch_time": 1_000_000,
                "delivery_time": 0,
            },
            {
                "symbol": "FUTURECOIN",
                "eligible": True,
                "launch_time": 2_000_000_000_000,
                "delivery_time": 0,
            },
        ]
    }
    pit = point_in_time_membership(snap, as_of_ms=1_500_000)
    assert pit == ["BTCUSDT"]
    assert "FUTURECOIN" not in pit


def test_instrument_pagination_contract_and_exclusions(monkeypatch):
    row = {
        "symbol": "BTCUSDT",
        "baseCoin": "BTC",
        "quoteCoin": "USDT",
        "settleCoin": "USDT",
        "status": "Trading",
        "contractType": "LinearPerpetual",
        "launchTime": "1000",
        "deliveryTime": "0",
        "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "minNotionalValue": "5"},
        "priceFilter": {"tickSize": "0.1"},
        "leverageFilter": {"maxLeverage": "100"},
    }
    snap = normalize_instrument(row, snapshot_timestamp="t")
    assert snap.eligible is True
    bad = dict(row)
    bad["status"] = "PreLaunch"
    assert normalize_instrument(bad, snapshot_timestamp="t").eligible is False

    calls: list[dict] = []

    def fake_get(path: str, params: dict, *, timeout: float = 20.0):
        calls.append(dict(params))
        if len(calls) == 1:
            return {
                "retCode": 0,
                "result": {
                    "list": [row],
                    "nextPageCursor": "page2",
                },
            }
        return {"retCode": 0, "result": {"list": [{**row, "symbol": "ETHUSDT"}], "nextPageCursor": ""}}

    import backend.nexus_dynamic_universe as du

    monkeypatch.setattr(du, "_get", fake_get)
    rows = du.fetch_all_linear_instruments()
    assert len(rows) == 2
    assert len(calls) == 2
    assert calls[1].get("cursor") == "page2"


def test_survivorship_bias_detection():
    snap = {
        "instruments": [
            {"symbol": "OLD", "eligible": True, "launch_time": 1, "delivery_time": 0},
            {"symbol": "NEW", "eligible": True, "launch_time": 9_999_999, "delivery_time": 0},
            {"symbol": "DEAD", "eligible": True, "launch_time": 1, "delivery_time": 100},
        ]
    }
    early = set(point_in_time_membership(snap, as_of_ms=50))
    after_dead = set(point_in_time_membership(snap, as_of_ms=150))
    late = set(point_in_time_membership(snap, as_of_ms=10_000_000))
    assert early == {"OLD", "DEAD"}  # delivery not yet reached
    assert "DEAD" not in after_dead
    assert "NEW" in late
    # Detect bias if someone uses late-only set for early fold
    assert early != late


def test_meme_unknown_without_taxonomy():
    assert classify_meme("DOGE", taxonomy_available=True) == "MEME"
    assert classify_meme("BTC", taxonomy_available=True) == "NON_MEME"
    assert classify_meme("DOGE", taxonomy_available=False) == "UNKNOWN"


def test_symbol_profile_determinism():
    from backend.nexus_dynamic_universe.symbol_profile import build_profiles

    instruments = [
        {
            "symbol": "AAAUSDT",
            "eligible": True,
            "base_coin": "AAA",
            "launch_time": 1,
        },
        {
            "symbol": "BBBUSDT",
            "eligible": True,
            "base_coin": "BBB",
            "launch_time": 1,
        },
    ]
    tickers = {
        "AAAUSDT": {"turnover24h": "100", "openInterestValue": "50", "bid1Price": "1", "ask1Price": "1.01", "lastPrice": "1"},
        "BBBUSDT": {"turnover24h": "10", "openInterestValue": "5", "bid1Price": "1", "ask1Price": "1.01", "lastPrice": "1"},
    }
    a = build_profiles(instruments=instruments, tickers=tickers, timestamp="t", as_of_ms=86_400_000 * 40)
    b = build_profiles(instruments=instruments, tickers=tickers, timestamp="t", as_of_ms=86_400_000 * 40)
    assert [p.to_dict() for p in a] == [p.to_dict() for p in b]
    assert a[0].market_size_class in {"MAINSTREAM", "MID_SIZE", "SMALL"}


def test_eligibility_before_performance():
    ok, fails = eligibility_gates(
        listing_age_days=5,
        coverage_ratio=0.5,
        turnover_24h=100,
        oi_value=None,
        spread_bps=50,
        slippage_bps=40,
        mark_status="MISSING",
        candle_status="MISSING",
    )
    assert ok is False
    assert "insufficient_listing_age" in fails


def test_ai_schema_compat_and_invalid_json_rejection():
    schema = {
        "title": "reason",
        "required": ["decision"],
        "properties": {"decision": {"type": "string"}},
    }
    assert validate_against_schema({"decision": "PASS"}, schema)
    assert not validate_against_schema({"decision": 1}, schema)
    assert not validate_against_schema({"extra": "x"}, schema)
    gw = AIGateway.from_env(mock_for_ci=True)
    bad = MockProvider("GROQ")
    bad.responses["reason"] = {"wrong": True}
    gw.providers["GROQ"] = bad
    parsed, rec, perm = gw.invoke_role(
        role="main_market_reasoner",
        model_id="m",
        prompt="hello",
        schema=schema,
        prompt_schema_version="v1",
    )
    assert parsed is None
    assert rec.result_status == "INVALID_SCHEMA"
    assert perm == "BLOCK"


def test_ai_rate_limit_and_unavailable_fail_closed():
    gw = AIGateway.from_env(mock_for_ci=True)
    gw.providers["GROQ"] = MockProvider("GROQ", force_status="RATE_LIMITED")
    schema = {"title": "default", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}
    parsed, rec, perm = gw.invoke_role(
        role="main_market_reasoner",
        model_id="m",
        prompt="x",
        schema=schema,
        prompt_schema_version="v1",
    )
    assert parsed is None and rec.result_status == "RATE_LIMITED" and perm == "BLOCK"
    gw.providers["GROQ"] = MockProvider("GROQ", available=False)
    parsed2, rec2, perm2 = gw.invoke_role(
        role="main_market_reasoner",
        model_id="m",
        prompt="x",
        schema=schema,
        prompt_schema_version="v1",
    )
    assert rec2.result_status == "PROVIDER_UNAVAILABLE" and perm2 == "BLOCK"


def test_external_prompt_secret_redaction():
    raw = "api_key=sk-abc123SECRET and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xx"
    red = redact_for_external(raw)
    assert "sk-abc123SECRET" not in red
    assert "Bearer eyJ" not in red
    assert "[REDACTED]" in red


def test_hard_risk_critic_cannot_be_overridden():
    out = deterministic_risk_critic(hard_blocks=["spread_above_limit"], ai_opinion="ALLOW_ANYWAY")
    assert out["blocked"] is True
    assert out["ai_override_allowed"] is False
    assert out["order_permission"] == "BLOCK"


def test_good_process_loss_no_automatic_policy_change():
    lesson = create_lesson_from_outcome(
        trade_id="t1",
        symbol="BTCUSDT",
        symbol_profile={},
        strategy_id="s",
        regime="TRENDING_DOWN",
        direction="Sell",
        pnl=-1.5,
        process_good=True,
        reflection_provider="GEMINI",
        reflection_model="m",
        critic_provider="GROQ",
        critic_model="m2",
    )
    assert lesson.process_classification == "GOOD_PROCESS_LOSS"
    assert lesson.proposed_policy_changes == []
    assert lesson.immediate_safe_actions == []


def test_bad_process_win_creates_negative_lesson():
    lesson = create_lesson_from_outcome(
        trade_id="t2",
        symbol="ETHUSDT",
        symbol_profile={},
        strategy_id="s",
        regime="TRENDING_DOWN",
        direction="Sell",
        pnl=2.0,
        process_good=False,
        reflection_provider="GEMINI",
        reflection_model="m",
        critic_provider="GROQ",
        critic_model="m2",
    )
    assert lesson.process_classification == "BAD_PROCESS_WIN"
    assert "require_additional_confirmation" in lesson.immediate_safe_actions


def test_lesson_retrieval_by_future_main_reasoner():
    mem = LessonMemory()
    lesson = create_lesson_from_outcome(
        trade_id="t3",
        symbol="SOLUSDT",
        symbol_profile={},
        strategy_id="trend",
        regime="R",
        direction="Sell",
        pnl=-1,
        process_good=False,
        reflection_provider="GEMINI",
        reflection_model="m",
        critic_provider="GROQ",
        critic_model="m2",
    )
    mem.add(lesson)
    app = main_reasoner_with_lessons(memory=mem, symbol="SOLUSDT", strategy_id="trend")
    assert lesson.lesson_id in app.retrieved_lesson_ids
    assert lesson.lesson_id in app.applied_lesson_ids


def test_temporary_control_cannot_become_permanent():
    mem = LessonMemory()
    lesson = create_lesson_from_outcome(
        trade_id="t4",
        symbol="XRPUSDT",
        symbol_profile={},
        strategy_id="s",
        regime="R",
        direction="Sell",
        pnl=-1,
        process_good=False,
        reflection_provider="GEMINI",
        reflection_model="m",
        critic_provider="GROQ",
        critic_model="m2",
    )
    mem.add(lesson)
    assert mem.temporary_control_is_permanent(lesson.lesson_id) is False
    for action in FORBIDDEN_IMMEDIATE:
        with pytest.raises(ValueError):
            bad = create_lesson_from_outcome(
                trade_id="t5",
                symbol="XRPUSDT",
                symbol_profile={},
                strategy_id="s",
                regime="R",
                direction="Sell",
                pnl=-1,
                process_good=False,
                reflection_provider="G",
                reflection_model="m",
                critic_provider="G",
                critic_model="m",
            )
            bad.immediate_safe_actions = [action]
            mem.add(bad)


def test_provider_model_change_invalidates_qualification_identity():
    a = qualification_identity(provider="GROQ", model="m1", policy_id="P")
    b = qualification_identity(provider="GROQ", model="m2", policy_id="P")
    assert a != b


def test_five_fold_chronological_walk_forward():
    rows = [{"entry_ts": i, "net_pnl": 0.1 if i % 2 else -0.1} for i in range(100)]
    folds = chronological_folds(rows, 5)
    assert len(folds) == 5
    # chronological: first fold earlier than last
    assert folds[0][0]["entry_ts"] < folds[-1][-1]["entry_ts"]


def test_fold_concentration_gate_not_lowered():
    assert H5_GATES["max_largest_profitable_fold_contribution"] == 0.60
    assert H5_GATES["fold_concentration_gate_not_lowered"] is True
    status = classify_h5(
        replay={
            "completed_trade_count": 200,
            "gross_expectancy": 0.5,
            "net_expectancy": 0.2,
            "net_profit_factor": 1.2,
        },
        adv={"net_profit_factor": 1.05},
        fold_ok=3,
        fold_usable=5,
        fold_positive=3,
        symbol_pos_share=0.1,
        fold_profit_share=0.75,
        data_valid=True,
    )
    assert status == "REJECTED_FOLD_CONCENTRATED"


def test_no_post_result_subgroup_promotion():
    pre = preregistration_payload()
    assert pre["post_result_subgroup_promotion_forbidden"] is True
    assert H5_GATES["post_result_subgroup_promotion_forbidden"] is True
    assert len(HYPOTHESES_H5) <= 3


def test_h5_walk_forward_cannot_start_demo():
    pre = preregistration_payload()
    assert pre["demo_cannot_start_from_wf_alone"] is True
    assert pre["september_oos_may_not_validate_h5"] is True


def test_september_h3_oos_cannot_validate_h5():
    with pytest.raises(RuntimeError, match="SEPTEMBER_PARTIAL"):
        assert_september_partial_excluded(".nexus_runtime/oos/OOS_H3_UNTOUCHED_V1_RESERVED/x.json")
    for h in HYPOTHESES_H5:
        assert "OOS_H3_UNTOUCHED_V1_RESERVED" in h["forbidden_sources_for_thresholds"] or (
            "september_h3_partial_oos" in h["forbidden_sources_for_thresholds"]
        )


def test_wallet_residual_remains_visible():
    sot = json.loads((ROOT / "artifacts/readiness/NEXUS_READINESS_SOT.json").read_text(encoding="utf-8"))
    # Field names may nest; check common locations
    text = json.dumps(sot)
    assert "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST" in text or "wallet" in text.lower()
    assert "-0.97052039" in text or "0.97052039" in text


def test_h5_prereg_checksum_stable():
    assert preregistration_checksum() == preregistration_checksum()
    mutated = preregistration_payload()
    mutated["hypotheses"][0]["parameter_values"]["min_move_to_cost"] = 99.0
    assert sha_obj(mutated) != preregistration_checksum()


def test_h4_sealed_not_softened_when_package_present():
    path = ROOT / "artifacts/readiness/immutable/dynamic_universe_ai_learning_h5_v1/h4_sealed_classifications.json"
    if not path.is_file():
        pytest.skip("package not generated yet")
    sealed = json.loads(path.read_text(encoding="utf-8"))
    assert sealed["H4A_EVENT_RETEST_CONTINUATION"]["founder_classification"] == "PROMISING_MECHANISM_NOT_PORTABLE"
    assert sealed["H4C_OI_FUNDING_CONFIRMED_CONTINUATION"]["founder_classification"] == (
        "POSITIVE_BASE_RESULT_NOT_COST_OR_FOLD_STABLE"
    )
    assert sealed["selected_h4_primary_policy"] is None
