"""V16-D Strategy Expert Router — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V16_D_STRATEGY_EXPERT_ROUTER"
SCHEMA_THREE_PASS = "FOUNDER_V16_D_STRATEGY_EXPERT_ROUTER_THREE_PASS"
CAMPAIGN_ID = "v16_d_strategy_expert_router"
LANE = "V16-D"
LANE_NAME = "STRATEGY_EXPERT_ROUTER"
BRANCH = "feature/v16-strategy-expert-router"
BASE_COMMIT = "f01407e5d7c7e4c00e0eb1616dc5ef74d91a58b5"
RANDOM_SEED = 20260806
FIXED_LEVERAGE = 25

EXPERT_IDS = (
    "TREND",
    "MEAN_REVERSION",
    "BREAKOUT",
    "LIQUIDATION",
    "FUNDING",
    "OPEN_INTEREST",
    "EVENT",
    "VOLATILITY",
    "CROSS_ASSET",
    "DEFENSIVE_NO_TRADE",
)

DECISION_SIDES = (
    "LONG",
    "SHORT",
    "WAIT",
    "REDUCE",
    "ABSTAIN",
)

NO_TRADE_SIDES = frozenset({"WAIT", "REDUCE", "ABSTAIN"})
DEFENSIVE_EXPERT = "DEFENSIVE_NO_TRADE"

# Regime probability keys consumed by the router (aligned with V16-C surface).
REGIME_PROB_KEYS = (
    "strong_bull_probability",
    "strong_bear_probability",
    "volatility_expansion_probability",
    "liquidity_stress_probability",
    "long_crowding_probability",
    "correlation_breakdown_probability",
    "event_risk_probability",
    "regime_transition_probability",
)

ROUTING_FACTORS = (
    "regime_probs",
    "data_trust",
    "execution_cost",
    "liquidity",
    "historical_stability",
    "uncertainty",
    "portfolio_exposure",
    "lesson_restrictions",
)

# Formal router params may not thrash faster than this dwell.
FORMAL_PARAM_MIN_DWELL_MS = 15 * 60 * 1000  # 15 minutes
EXPERT_COOLDOWN_MS = 5 * 60 * 1000
EXPERT_DEGRADATION_THRESHOLD = 3  # consecutive soft failures before degrade
MIN_DATA_TRUST = 0.45
MAX_UNCERTAINTY_FOR_ENTRY = 0.72
MAX_COST_BPS_FOR_ENTRY = 35.0
MIN_LIQUIDITY_SCORE = 0.35
MAX_PORTFOLIO_EXPOSURE = 0.85

HARD_BANS = frozenset(
    {
        "no_ai_set_leverage",
        "no_ai_override_risk_gate",
        "no_status_json_lane_artifact",
        "no_status_report_artifact",
        "no_per_minute_formal_param_thrash",
        "no_exchange_write",
        "no_demo_orders",
        "no_shadow_orders",
        "no_mainnet",
        "no_real_money",
        "no_oos_consumption",
        "no_formal_walk_forward",
        "no_strategy_promotion_to_live",
        "no_auto_integrate_pr27",
        "no_pr27_merge",
        "no_profitability_claims",
        "no_force_trade_when_defensive_wins",
        "no_suppress_no_trade_sides",
    }
)

OWNED_PATHS = [
    "backend/nexus_strategy_expert_router",
    "tests/strategy_expert_router",
]

CHAMPION_ROLE = "SHADOW_CHAMPION"
CHALLENGER_ROLE = "SHADOW_CHALLENGER"
FORBIDDEN_PROMOTION = frozenset({"LIVE_APPLIED", "AUTO_PROMOTED", "PRODUCTION"})

NON_CLAIMS = (
    "No live strategy promotion",
    "No profitability claim",
    "No AI leverage mutation",
    "No Risk Gate override",
    "Routing research / shadow decision surface only",
)
