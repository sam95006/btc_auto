"""V14-F Regime and Cross-Asset Lab — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V14_F_REGIME_CROSS_ASSET_LAB"
REGIME_SCHEMA_VERSION = "regime_lab_v14_f_1"
CATALOG_VERSION = "v14_f_regime_catalog_1"
LANE = "V14-F"
LANE_NAME = "REGIME_AND_CROSS_ASSET_LAB"
BRANCH = "feature/v14-regime-cross-asset-lab"
BASE_COMMIT = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"

# Default observation bar / lookback (exchange time).
DEFAULT_BAR_MS = 60_000
DEFAULT_LOOKBACK_BARS = 20
DEFAULT_STALE_AFTER_MS = 180_000
DEFAULT_LEAD_LAG_MAX_LAG_BARS = 5

REGIME_IDS = (
    "volatility_regime",
    "liquidity_regime",
    "trend_regime",
    "funding_regime",
    "open_interest_regime",
    "liquidation_regime",
    "correlation_regime",
    "market_stress_regime",
)

HARD_BANS = {
    "predictive_edge_claims": False,
    "fabricated_strategy_edge": False,
    "profit_guarantee": False,
    "silent_seal_or_modify_old_raw_partitions": False,
    "event_study": False,
    "demo_orders": False,
    "shadow_orders": False,
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "pr27_merge": False,
    "formal_walk_forward": False,
    "oos_execution": False,
    "strategy_promotion": False,
    "auto_integrate": False,
}

OWNED_PATHS = [
    "backend/nexus_regime_lab",
    "tools/research/regime_lab",
    "tests/regime_lab",
    "artifacts/readiness/immutable/v14_regime_lab",
]

NON_CLAIMS = (
    "No predictive edge",
    "No profitability",
    "No strategy signal",
    "No lead-lag trading claim",
    "Descriptive Point-in-Time regime measurement and lead-lag research only",
)
