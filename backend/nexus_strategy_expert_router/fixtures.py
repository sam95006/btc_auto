"""Synthetic fixtures for V16-D Strategy Expert Router."""
from __future__ import annotations

from backend.nexus_strategy_expert_router.models import MarketContext, RegimeProbabilities


def _base_ts() -> int:
    return 1_720_000_000_000


def fixture_strong_trend_long() -> MarketContext:
    return MarketContext(
        symbol="BTCUSDT",
        ts_ms=_base_ts(),
        regime=RegimeProbabilities(
            strong_bull_probability=0.78,
            strong_bear_probability=0.08,
            volatility_expansion_probability=0.25,
            liquidity_stress_probability=0.10,
            long_crowding_probability=0.30,
            correlation_breakdown_probability=0.12,
            event_risk_probability=0.05,
            regime_transition_probability=0.10,
            regime_confidence=0.85,
            regime_freshness=0.95,
        ),
        data_trust=0.88,
        execution_cost_bps=8.0,
        liquidity_score=0.82,
        historical_stability=0.75,
        uncertainty=0.25,
        portfolio_exposure=0.20,
    )


def fixture_mean_reversion_crowding() -> MarketContext:
    return MarketContext(
        symbol="ETHUSDT",
        ts_ms=_base_ts() + 60_000,
        regime=RegimeProbabilities(
            strong_bull_probability=0.55,
            strong_bear_probability=0.15,
            volatility_expansion_probability=0.20,
            liquidity_stress_probability=0.12,
            long_crowding_probability=0.82,
            correlation_breakdown_probability=0.10,
            event_risk_probability=0.08,
            regime_transition_probability=0.15,
            regime_confidence=0.70,
            regime_freshness=0.90,
        ),
        data_trust=0.80,
        execution_cost_bps=10.0,
        liquidity_score=0.75,
        historical_stability=0.80,
        uncertainty=0.30,
        portfolio_exposure=0.25,
    )


def fixture_defensive_stress() -> MarketContext:
    return MarketContext(
        symbol="BTCUSDT",
        ts_ms=_base_ts() + 120_000,
        regime=RegimeProbabilities(
            strong_bull_probability=0.20,
            strong_bear_probability=0.22,
            volatility_expansion_probability=0.70,
            liquidity_stress_probability=0.85,
            long_crowding_probability=0.40,
            correlation_breakdown_probability=0.65,
            event_risk_probability=0.75,
            regime_transition_probability=0.80,
            regime_confidence=0.40,
            regime_freshness=0.55,
        ),
        data_trust=0.42,
        execution_cost_bps=40.0,
        liquidity_score=0.25,
        historical_stability=0.30,
        uncertainty=0.88,
        portfolio_exposure=0.70,
    )


def fixture_risk_gate_blocked() -> MarketContext:
    ctx = fixture_strong_trend_long()
    return MarketContext(
        symbol=ctx.symbol,
        ts_ms=ctx.ts_ms + 180_000,
        regime=ctx.regime,
        data_trust=ctx.data_trust,
        execution_cost_bps=ctx.execution_cost_bps,
        liquidity_score=ctx.liquidity_score,
        historical_stability=ctx.historical_stability,
        uncertainty=ctx.uncertainty,
        portfolio_exposure=ctx.portfolio_exposure,
        risk_gate_allow=False,
        risk_gate_reason="MAX_DRAWDOWN_BUDGET",
        requested_leverage=100,
    )


def fixture_lesson_forced_abstain() -> MarketContext:
    ctx = fixture_strong_trend_long()
    return MarketContext(
        symbol=ctx.symbol,
        ts_ms=ctx.ts_ms + 240_000,
        regime=ctx.regime,
        data_trust=ctx.data_trust,
        execution_cost_bps=ctx.execution_cost_bps,
        liquidity_score=ctx.liquidity_score,
        historical_stability=ctx.historical_stability,
        uncertainty=ctx.uncertainty,
        portfolio_exposure=ctx.portfolio_exposure,
        lesson_blocked_experts=("TREND", "BREAKOUT"),
        lesson_forced_abstain=True,
    )


def fixture_low_trust() -> MarketContext:
    ctx = fixture_strong_trend_long()
    return MarketContext(
        symbol=ctx.symbol,
        ts_ms=ctx.ts_ms + 300_000,
        regime=ctx.regime,
        data_trust=0.20,
        execution_cost_bps=ctx.execution_cost_bps,
        liquidity_score=ctx.liquidity_score,
        historical_stability=0.40,
        uncertainty=0.90,
        portfolio_exposure=ctx.portfolio_exposure,
    )


def all_fixtures() -> dict[str, MarketContext]:
    return {
        "strong_trend_long": fixture_strong_trend_long(),
        "mean_reversion_crowding": fixture_mean_reversion_crowding(),
        "defensive_stress": fixture_defensive_stress(),
        "risk_gate_blocked": fixture_risk_gate_blocked(),
        "lesson_forced_abstain": fixture_lesson_forced_abstain(),
        "low_trust": fixture_low_trust(),
    }
