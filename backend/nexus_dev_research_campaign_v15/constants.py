"""V15-C Real Development Research Campaign — constants & hard bans."""
from __future__ import annotations

PACKAGE = "NEXUS_REAL_DEVELOPMENT_RESEARCH_CAMPAIGN_V15_C"
SCHEMA = "v15_c_real_development_research_campaign"
CAMPAIGN_ID = "v15_c_real_development_research_campaign"
ARTIFACT_DIRNAME = "v15_c_real_development_research_campaign"
LANE = "V15-C"
LANE_NAME = "REAL_DEVELOPMENT_RESEARCH_CAMPAIGN"
BRANCH = "feature/v15-real-development-research-campaign"
BASE_COMMIT = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"
RANDOM_SEED = 20260805

DEVELOPMENT_INTERVAL_ID = "DEV_REAL_HISTORICAL_V15C_2026_04_04_TO_2026_08_02"
# From edge_discovery development_interval_registry v1_2 window (exclusive of OOS).
DEV_START_MS = 1_775_295_000_000  # 2026-04-04T09:30:00Z
DEV_END_MS = 1_785_663_000_000  # 2026-08-02T09:30:00Z
# Untouched OOS reservation — must never be consumed.
OOS_RESERVED_START_MS = 1_785_663_000_001
OOS_RESERVED_END_MS = 1_789_551_000_000

HARD_BANS = frozenset(
    {
        "no_oos_consumption",
        "no_formal_walk_forward",
        "no_demo_orders",
        "no_shadow_orders",
        "no_exchange_write",
        "no_mainnet",
        "no_real_money",
        "no_profitability_claims",
        "no_qualified_claims",
        "no_strategy_promotion",
        "no_pr27_merge",
        "no_auto_integrate",
        "no_status_json_emit",
    }
)

ALLOWED_LABELS = frozenset(
    {
        "REJECTED",
        "DATA_BLOCKED",
        "SAMPLE_BLOCKED",
        "COST_DESTROYED",
        "REGIME_FRAGILE",
        "MULTIPLE_TESTING_REJECTED",
        "DEVELOPMENT_REVIEW",
        "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
    }
)

BANNED_LABEL_FRAGMENTS = frozenset(
    {
        "QUALIFIED",
        "PROFITABLE",
        "OOS_PASS",
        "WALK_FORWARD_PASS",
        "DEMO_READY",
        "PROMOTION_READY",
        "PROMOTED",
    }
)

OWNED_PATHS = [
    "backend/nexus_dev_research_campaign_v15/",
    "tools/research/dev_research_campaign_v15/",
    "tests/dev_research_campaign_v15/",
    "artifacts/readiness/immutable/v15_c_real_development_research_campaign/",
]

# Research symbols / bars — development classified only.
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
DEFAULT_INTERVAL = "60"

# Gates
MIN_SAMPLE_TRADES = 12
MIN_SAMPLE_OBSERVATIONS = 48
REGIME_FRAGILITY_SHARE = 0.55
FDR_Q_LEVEL = 0.10
BONFERRONI_ALPHA = 0.05

# Features that can be derived from public development klines (+ funding/OI).
DERIVABLE_FEATURES = frozenset(
    {
        "mid",
        "mid_return",
        "exchange_ts_ms",
        "receive_ts_ms",
        "range_expansion",
        "range_compression",
        "range_compression_lag",
        "range_high_break",
        "range_low_break",
        "volume_z",
        "volume_price_divergence",
        "tod_hour_utc",
        "tod_session_bucket",
        "funding_z",
        "funding_rate",
        "oi_change",
        "lead_return",
        "lag_return",
        "lead_lag_score",
        "cross_corr",
        "pair_residual",
        "distance_to_level_bps",
        "breakout_fail_flag",
        "realized_vol",
        "spread_bps_range_proxy",
    }
)

# Explicit proxy note — never claim book/micro fidelity for range-derived spread.
SPREAD_PROXY_NOTE = "spread_bps_range_proxy_from_hl_range_NOT_top_of_book"

NON_CLAIMS = (
    "No predictive edge claim",
    "No stable profitability claim",
    "No qualification claim",
    "Development-classified research surface only",
    "qualification_ready_count must remain 0",
    "Fixtures, if used, are never labeled REAL",
)
