"""V13-D Dynamic Market Discovery — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V13_D_DYNAMIC_MARKET_DISCOVERY"
DISCOVERY_SCHEMA = "nexus_pit_market_discovery_v1"
LINEAGE_SCHEMA = "nexus_pit_market_discovery_lineage_v1"
UNIVERSE_ID = "NEXUS_PIT_DYNAMIC_LINEAR_USDT_UNIVERSE"

LANE = "V13-D"
LANE_NAME = "DYNAMIC_MARKET_DISCOVERY"
BRANCH = "feature/v13-dynamic-market-discovery"
BASE_COMMIT = "abd2195ef6d79f609dd261b5e9c5402599625a64"

# Hard bans — never violated by this lane
HARD_BANS = (
    "no_exchange_writes",
    "no_demo",
    "no_pr27_merge",
    "no_today_universe_for_past_as_of",
    "no_future_observation_leak",
)

EVALUATION_DIMENSIONS = (
    "availability",
    "listing_timestamp",
    "delisting_state",
    "liquidity",
    "volume",
    "spread",
    "depth",
    "open_interest",
    "funding_availability",
    "data_completeness",
    "staleness",
    "symbol_mapping",
    "contract_specification",
    "minimum_notional",
    "tick_size",
    "quantity_step",
)

REJECTION_REASONS = (
    "NOT_AVAILABLE",
    "NOT_YET_LISTED",
    "DELISTED",
    "INSUFFICIENT_LIQUIDITY",
    "INSUFFICIENT_VOLUME",
    "SPREAD_TOO_WIDE",
    "INSUFFICIENT_DEPTH",
    "OPEN_INTEREST_MISSING_OR_LOW",
    "FUNDING_UNAVAILABLE",
    "INCOMPLETE_DATA",
    "STALE_OBSERVATION",
    "MAPPING_MISSING",
    "INVALID_CONTRACT_SPEC",
    "INVALID_MIN_NOTIONAL",
    "INVALID_TICK_SIZE",
    "INVALID_QTY_STEP",
    "FUTURE_OBSERVATION_LEAK",
    "WRONG_SNAPSHOT_ERA",
    "OTHER_EXPLICIT",
)

# Default eligibility thresholds (sanitized research defaults)
DEFAULT_THRESHOLDS = {
    "min_liquidity_score": 0.35,
    "min_turnover_usdt": 500_000.0,
    "min_volume_usdt": 250_000.0,
    "max_spread_bps": 25.0,
    "min_depth_usdt": 25_000.0,
    "min_open_interest_usdt": 100_000.0,
    "min_completeness": 0.85,
    "max_staleness_ms": 3_600_000,  # 1h
    "require_funding": True,
    "require_oi": True,
}

OWNED_PATHS = (
    "backend/nexus_market_discovery",
    "tools/research/run_dynamic_market_discovery_v13.py",
    "tests/test_dynamic_market_discovery_v13.py",
    "artifacts/readiness/immutable/v13_dynamic_market_discovery",
)
