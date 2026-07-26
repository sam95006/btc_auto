"""Tests for demo strategy evaluator and capital allocator.

Fixtures for various equity sizes, stop distances, fee/slippage/funding.
Asserts allow_trade=false when gates fail.
Asserts VALIDATION tier for first order path.
"""
from __future__ import annotations

import pytest

from backend.nexus_research.demo_strategy.candidate_ranking import (
    STRATEGY_CANDIDATE_RANKING,
    get_candidates_for_symbol,
    ranked_symbols,
)
from backend.nexus_research.demo_strategy.capital_allocator import (
    AUTO_ADD_MARGIN,
    DEFAULT_LEVERAGE,
    LEVERAGE_OPTIONS,
    MARGIN_MODE,
    MAX_OPEN_DEMO_POSITIONS,
    NO_AVERAGING_DOWN,
    NO_MARTINGALE,
    DemoCapitalAllocator,
    DemoPositionSizer,
    DemoRiskBudget,
    FeeSlippageBuffer,
    LeverageSelector,
    LiquidationDistanceGuard,
    MarginRequirementCalculator,
    PortfolioExposureController,
)
from backend.nexus_research.demo_strategy.market_features import (
    FIXTURE_BTCUSDT,
    FIXTURE_ETHUSDT,
    FIXTURE_SOLUSDT,
    MarketFeatures,
    extract_features,
)
from backend.nexus_research.demo_strategy.risk_tiers import (
    ACCELERATED_TIER,
    BASE_TIER,
    GROWTH_TIER,
    VALIDATION_TIER,
    RiskTierName,
    first_order_tier,
    get_tier,
)
from backend.nexus_research.demo_strategy.strategy_evaluator import (
    evaluate,
    evaluate_all,
)


# ── Feature extraction ────────────────────────────────────────────────────────

class TestMarketFeatures:
    def test_extract_btc_fixture(self):
        f = extract_features(FIXTURE_BTCUSDT, source="fixture")
        assert f.symbol == "BTCUSDT"
        assert f.source == "fixture"
        assert f.rsi_14 == 58.0
        assert f.spread_bps == 1.2
        assert not f.is_stale()

    def test_extract_eth_fixture(self):
        f = extract_features(FIXTURE_ETHUSDT, source="fixture")
        assert f.symbol == "ETHUSDT"
        assert f.regime in ("TRENDING_UP", "RANGING", "UNKNOWN")

    def test_extract_sol_fixture(self):
        f = extract_features(FIXTURE_SOLUSDT, source="fixture")
        assert f.symbol == "SOLUSDT"
        assert f.atr_pct == 3.5

    def test_stale_detection(self):
        data = {**FIXTURE_BTCUSDT, "data_age_ms": 200_000}
        f = extract_features(data)
        assert f.is_stale(max_age_ms=120_000)

    def test_regime_volatile(self):
        data = {**FIXTURE_BTCUSDT, "atr_pct": 6.0}
        f = extract_features(data)
        assert f.regime == "VOLATILE"

    def test_regime_ranging(self):
        data = {**FIXTURE_BTCUSDT, "trend_score": 5, "momentum_score": 3, "atr_pct": 1.0}
        f = extract_features(data)
        assert f.regime == "RANGING"

    def test_missing_optional_fields(self):
        f = extract_features({"symbol": "XYZUSDT"})
        assert f.symbol == "XYZUSDT"
        assert f.rsi_14 is None
        assert f.funding_rate_8h_pct is None

    def test_to_dict_has_research_only(self):
        f = extract_features(FIXTURE_BTCUSDT)
        d = f.to_dict()
        assert d["researchOnly"] is True
        assert "symbol" in d


# ── Risk Tiers ────────────────────────────────────────────────────────────────

class TestRiskTiers:
    def test_validation_tier_range(self):
        assert VALIDATION_TIER.min_risk_pct == 0.25
        assert VALIDATION_TIER.max_risk_pct == 0.50

    def test_base_tier_range(self):
        assert BASE_TIER.min_risk_pct == 0.50
        assert BASE_TIER.max_risk_pct == 0.75

    def test_growth_tier_range(self):
        assert GROWTH_TIER.min_risk_pct == 0.75
        assert GROWTH_TIER.max_risk_pct == 1.00

    def test_accelerated_tier_range(self):
        assert ACCELERATED_TIER.min_risk_pct == 1.00
        assert ACCELERATED_TIER.max_risk_pct == 1.25

    def test_first_order_must_be_validation(self):
        tier = first_order_tier()
        assert tier.name == RiskTierName.VALIDATION

    def test_clamp_above_max(self):
        clamped = VALIDATION_TIER.clamp(2.0)
        assert clamped == 0.50

    def test_clamp_below_min(self):
        clamped = VALIDATION_TIER.clamp(0.1)
        assert clamped == 0.25

    def test_get_tier_by_string(self):
        t = get_tier("VALIDATION")
        assert t == VALIDATION_TIER


# ── Candidate Ranking ────────────────────────────────────────────────────────

class TestCandidateRanking:
    def test_ranking_has_three_symbols(self):
        assert len(STRATEGY_CANDIDATE_RANKING) == 3

    def test_btc_is_priority_1(self):
        btc = get_candidates_for_symbol("BTCUSDT")
        assert len(btc) == 1
        assert btc[0].priority == 1

    def test_sol_long_only(self):
        sol = get_candidates_for_symbol("SOLUSDT")
        assert sol[0].direction == "LONG"

    def test_ranked_symbols_order(self):
        syms = ranked_symbols()
        assert syms == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


# ── Strategy Evaluator ───────────────────────────────────────────────────────

class TestStrategyEvaluator:
    def test_btc_long_passes(self):
        features = extract_features(FIXTURE_BTCUSDT, source="fixture")
        result = evaluate(features, "LONG")
        assert result.symbol == "BTCUSDT"
        assert result.direction == "LONG"
        assert result.composite_score > 0
        assert result.risk_critic_pass is True

    def test_critic_blocks_overbought_rsi(self):
        data = {**FIXTURE_BTCUSDT, "rsi_14": 85.0}
        features = extract_features(data, source="fixture")
        result = evaluate(features, "LONG")
        assert result.risk_critic_pass is False
        assert result.allow_trade is False
        assert any("overbought" in r.lower() for r in result.block_reasons)

    def test_critic_blocks_oversold_rsi_for_short(self):
        data = {**FIXTURE_BTCUSDT, "rsi_14": 18.0}
        features = extract_features(data, source="fixture")
        result = evaluate(features, "SHORT")
        assert result.risk_critic_pass is False
        assert result.allow_trade is False

    def test_critic_blocks_wide_spread(self):
        data = {**FIXTURE_BTCUSDT, "spread_bps": 20.0}
        features = extract_features(data, source="fixture")
        result = evaluate(features, "LONG")
        assert result.risk_critic_pass is False
        assert any("spread" in r.lower() for r in result.block_reasons)

    def test_critic_blocks_stale_data(self):
        data = {**FIXTURE_BTCUSDT, "data_age_ms": 200_000}
        features = extract_features(data, source="fixture")
        result = evaluate(features, "LONG")
        assert result.risk_critic_pass is False
        assert result.allow_trade is False

    def test_critic_blocks_low_volume(self):
        data = {**FIXTURE_BTCUSDT, "volume_24h": 100_000_000}
        features = extract_features(data, source="fixture")
        result = evaluate(features, "LONG")
        assert result.risk_critic_pass is False

    def test_sol_short_blocked_by_direction(self):
        features = extract_features(FIXTURE_SOLUSDT, source="fixture")
        result = evaluate(features, "SHORT")
        assert result.allow_trade is False
        assert any(
            "direction" in r.lower() or "no candidate" in r.lower()
            for r in result.block_reasons
        )

    def test_evaluate_all_returns_sorted(self):
        results = evaluate_all()
        assert len(results) >= 3
        scores = [r.composite_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_evaluation_result_to_dict(self):
        features = extract_features(FIXTURE_BTCUSDT, source="fixture")
        result = evaluate(features, "LONG")
        d = result.to_dict()
        assert d["researchOnly"] is True
        assert "compositeScore" in d
        assert "allowTrade" in d

    def test_never_lower_gates(self):
        """Confirm gates are not lowered even for high-score candidates."""
        data = {
            **FIXTURE_BTCUSDT,
            "rsi_14": 82.0,
            "trend_score": 90.0,
            "momentum_score": 90.0,
        }
        features = extract_features(data, source="fixture")
        result = evaluate(features, "LONG")
        assert result.risk_critic_pass is False
        assert result.allow_trade is False


# ── Capital Allocator Components ──────────────────────────────────────────────

class TestDemoRiskBudget:
    def test_validation_tier_budget(self):
        budget = DemoRiskBudget()
        r = budget.compute(10_000, VALIDATION_TIER)
        assert r.risk_pct == 0.50
        assert r.risk_amount_usd == 50.0

    def test_base_tier_budget(self):
        budget = DemoRiskBudget()
        r = budget.compute(10_000, "BASE")
        assert r.risk_pct == 0.75
        assert r.risk_amount_usd == 75.0

    def test_small_equity(self):
        budget = DemoRiskBudget()
        r = budget.compute(500, VALIDATION_TIER)
        assert r.risk_amount_usd == 2.50

    def test_large_equity(self):
        budget = DemoRiskBudget()
        r = budget.compute(100_000, ACCELERATED_TIER)
        assert r.risk_amount_usd == 1_250.0


class TestDemoPositionSizer:
    def test_basic_sizing(self):
        sizer = DemoPositionSizer()
        r = sizer.compute(risk_amount_usd=50.0, entry_price=100_000.0, stop_distance_pct=1.0)
        assert r.qty > 0
        assert r.notional > 0
        assert r.stop_distance_pct == 1.0

    def test_zero_stop_returns_zero(self):
        sizer = DemoPositionSizer()
        r = sizer.compute(risk_amount_usd=50.0, entry_price=100_000.0, stop_distance_pct=0.0)
        assert r.qty == 0.0

    def test_zero_price_returns_zero(self):
        sizer = DemoPositionSizer()
        r = sizer.compute(risk_amount_usd=50.0, entry_price=0.0, stop_distance_pct=1.0)
        assert r.qty == 0.0

    def test_tight_stop_larger_qty(self):
        sizer = DemoPositionSizer()
        r_tight = sizer.compute(50.0, 100_000.0, 0.5)
        r_wide = sizer.compute(50.0, 100_000.0, 2.0)
        assert r_tight.qty > r_wide.qty


class TestLeverageSelector:
    def test_default_25x(self):
        sel = LeverageSelector()
        r = sel.select(requested=25, stop_distance_pct=1.0)
        assert r.selected == 25

    def test_downgrade_when_unsafe(self):
        sel = LeverageSelector()
        r = sel.select(requested=35, stop_distance_pct=2.5)
        assert r.selected <= 35
        assert r.downgraded or r.selected == 35

    def test_zero_when_no_safe_option(self):
        sel = LeverageSelector(options=(50, 60, 70))
        r = sel.select(requested=70, stop_distance_pct=1.5, min_liq_distance_pct=3.0)
        assert r.selected == 0


class TestLiquidationDistanceGuard:
    def test_safe_at_25x(self):
        guard = LiquidationDistanceGuard()
        r = guard.check(leverage=25, stop_distance_pct=1.0)
        assert r.safe is True
        assert r.liq_distance_pct == 4.0

    def test_unsafe_at_high_leverage(self):
        guard = LiquidationDistanceGuard()
        r = guard.check(leverage=50, stop_distance_pct=1.5)
        assert r.safe is False


class TestFeeSlippageBuffer:
    def test_basic_buffer(self):
        buf = FeeSlippageBuffer()
        r = buf.compute(10_000.0)
        assert r.fee_estimate_usd > 0
        assert r.slippage_estimate_usd > 0
        assert r.total_buffer_usd > 0

    def test_larger_notional_larger_buffer(self):
        buf = FeeSlippageBuffer()
        r_small = buf.compute(1_000.0)
        r_large = buf.compute(100_000.0)
        assert r_large.total_buffer_usd > r_small.total_buffer_usd

    def test_custom_funding(self):
        buf = FeeSlippageBuffer()
        r = buf.compute(10_000.0, funding_rate=0.001, funding_periods=6)
        assert r.funding_reserve_usd == pytest.approx(60.0, abs=0.01)


class TestPortfolioExposureController:
    def test_allows_first_position(self):
        ctrl = PortfolioExposureController()
        r = ctrl.check(current_open=0)
        assert r.allowed is True

    def test_blocks_when_max_reached(self):
        ctrl = PortfolioExposureController(max_positions=1)
        r = ctrl.check(current_open=1)
        assert r.allowed is False


# ── Full Allocator Orchestration ──────────────────────────────────────────────

class TestDemoCapitalAllocator:
    @pytest.fixture
    def allocator(self):
        return DemoCapitalAllocator()

    def test_first_order_uses_validation_tier(self, allocator):
        decision = allocator.allocate(
            symbol="BTCUSDT", direction="LONG",
            entry_price=100_000.0, stop_distance_pct=1.0,
            equity=10_000.0, is_first_order=True,
        )
        assert decision.risk_tier == "VALIDATION"
        assert decision.risk_pct <= 0.50

    def test_allow_trade_true_for_good_setup(self, allocator):
        decision = allocator.allocate(
            symbol="BTCUSDT", direction="LONG",
            entry_price=100_000.0, stop_distance_pct=1.0,
            equity=10_000.0, is_first_order=True,
        )
        assert decision.allow_trade is True
        assert decision.qty > 0

    def test_blocked_when_max_positions_reached(self, allocator):
        decision = allocator.allocate(
            symbol="BTCUSDT", direction="LONG",
            entry_price=100_000.0, stop_distance_pct=1.0,
            equity=10_000.0, current_open_positions=1,
        )
        assert decision.allow_trade is False
        assert any("max" in r.lower() for r in decision.block_reasons)

    def test_small_equity_500(self, allocator):
        decision = allocator.allocate(
            symbol="BTCUSDT", direction="LONG",
            entry_price=100_000.0, stop_distance_pct=1.0,
            equity=500.0, is_first_order=True,
        )
        assert decision.risk_amount_usd == pytest.approx(2.50, abs=0.01)

    def test_large_equity_100k(self, allocator):
        decision = allocator.allocate(
            symbol="BTCUSDT", direction="LONG",
            entry_price=100_000.0, stop_distance_pct=1.0,
            equity=100_000.0, tier="GROWTH",
        )
        assert decision.risk_tier == "GROWTH"
        assert decision.risk_amount_usd == pytest.approx(1_000.0, abs=0.01)

    def test_wide_stop_smaller_position(self, allocator):
        d_tight = allocator.allocate(
            "BTCUSDT", "LONG", 100_000.0, 0.5, 10_000.0, is_first_order=True,
        )
        d_wide = allocator.allocate(
            "BTCUSDT", "LONG", 100_000.0, 3.0, 10_000.0, is_first_order=True,
        )
        assert d_tight.qty > d_wide.qty

    def test_isolated_margin_mode(self, allocator):
        decision = allocator.allocate(
            "BTCUSDT", "LONG", 100_000.0, 1.0, 10_000.0,
        )
        assert decision.margin_mode == "ISOLATED"
        assert decision.auto_add_margin is False

    def test_no_averaging_down_no_martingale(self, allocator):
        decision = allocator.allocate(
            "BTCUSDT", "LONG", 100_000.0, 1.0, 10_000.0,
        )
        assert decision.no_averaging_down is True
        assert decision.no_martingale is True

    def test_to_dict_has_research_only(self, allocator):
        decision = allocator.allocate(
            "BTCUSDT", "LONG", 100_000.0, 1.0, 10_000.0,
        )
        d = decision.to_dict()
        assert d["researchOnly"] is True
        assert d["marginMode"] == "ISOLATED"

    def test_equity_insufficient_blocks(self, allocator):
        decision = allocator.allocate(
            symbol="BTCUSDT", direction="LONG",
            entry_price=100_000.0, stop_distance_pct=1.0,
            equity=1.0, tier="ACCELERATED",
        )
        assert decision.risk_amount_usd < 0.02
        assert decision.notional < 2.0

    def test_eth_allocation(self, allocator):
        decision = allocator.allocate(
            symbol="ETHUSDT", direction="LONG",
            entry_price=3_500.0, stop_distance_pct=1.5,
            equity=10_000.0, is_first_order=True,
        )
        assert decision.symbol == "ETHUSDT"
        assert decision.risk_tier == "VALIDATION"

    def test_sol_allocation(self, allocator):
        decision = allocator.allocate(
            symbol="SOLUSDT", direction="LONG",
            entry_price=180.0, stop_distance_pct=2.0,
            equity=10_000.0, tier="BASE",
        )
        assert decision.symbol == "SOLUSDT"
        assert decision.qty > 0

    def test_fee_buffer_included(self, allocator):
        decision = allocator.allocate(
            "BTCUSDT", "LONG", 100_000.0, 1.0, 10_000.0,
        )
        assert decision.fee_buffer_usd > 0

    def test_leverage_downgrade_path(self, allocator):
        decision = allocator.allocate(
            "BTCUSDT", "LONG", 100_000.0, 2.5, 10_000.0,
            requested_leverage=35,
        )
        assert decision.leverage <= 35

    def test_source_fixture_label(self, allocator):
        decision = allocator.allocate(
            "BTCUSDT", "LONG", 100_000.0, 1.0, 10_000.0,
            source="fixture",
        )
        assert decision.source == "fixture"

    def test_source_live_label(self, allocator):
        decision = allocator.allocate(
            "BTCUSDT", "LONG", 100_000.0, 1.0, 10_000.0,
            source="live",
        )
        assert decision.source == "live"


# ── Defaults Assertions ──────────────────────────────────────────────────────

class TestDefaults:
    def test_margin_mode_isolated(self):
        assert MARGIN_MODE == "ISOLATED"

    def test_max_open_demo_positions_one(self):
        assert MAX_OPEN_DEMO_POSITIONS == 1

    def test_no_averaging_down(self):
        assert NO_AVERAGING_DOWN is True

    def test_no_martingale(self):
        assert NO_MARTINGALE is True

    def test_auto_add_margin_false(self):
        assert AUTO_ADD_MARGIN is False

    def test_default_leverage_25(self):
        assert DEFAULT_LEVERAGE == 25

    def test_leverage_options(self):
        assert set(LEVERAGE_OPTIONS) == {25, 30, 35}
