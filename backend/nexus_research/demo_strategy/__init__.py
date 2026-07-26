"""Demo strategy — strategy evaluation and capital allocation.

TRACK 3-4: Pure local computation. No orders. No secrets.
Leverage does NOT decide max loss — Risk Budget does.
"""
from __future__ import annotations

from backend.nexus_research.demo_strategy.candidate_ranking import (
    STRATEGY_CANDIDATE_RANKING,
    StrategyCandidate,
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
    AllocationDecision,
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
    RISK_TIERS,
    TIER_PROGRESSION,
    VALIDATION_TIER,
    RiskTier,
    RiskTierName,
    first_order_tier,
    get_tier,
)
from backend.nexus_research.demo_strategy.strategy_evaluator import (
    EvaluationResult,
    evaluate,
    evaluate_all,
)

RESEARCH_ONLY: bool = True

__all__ = [
    "ACCELERATED_TIER",
    "AUTO_ADD_MARGIN",
    "AllocationDecision",
    "BASE_TIER",
    "DEFAULT_LEVERAGE",
    "DemoCapitalAllocator",
    "DemoPositionSizer",
    "DemoRiskBudget",
    "EvaluationResult",
    "FIXTURE_BTCUSDT",
    "FIXTURE_ETHUSDT",
    "FIXTURE_SOLUSDT",
    "FeeSlippageBuffer",
    "GROWTH_TIER",
    "LEVERAGE_OPTIONS",
    "LeverageSelector",
    "LiquidationDistanceGuard",
    "MARGIN_MODE",
    "MAX_OPEN_DEMO_POSITIONS",
    "MarginRequirementCalculator",
    "MarketFeatures",
    "NO_AVERAGING_DOWN",
    "NO_MARTINGALE",
    "PortfolioExposureController",
    "RESEARCH_ONLY",
    "RISK_TIERS",
    "RiskTier",
    "RiskTierName",
    "STRATEGY_CANDIDATE_RANKING",
    "StrategyCandidate",
    "TIER_PROGRESSION",
    "VALIDATION_TIER",
    "evaluate",
    "evaluate_all",
    "extract_features",
    "first_order_tier",
    "get_candidates_for_symbol",
    "get_tier",
    "ranked_symbols",
]
