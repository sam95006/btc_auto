"""V18-C Live Eligible Universe Engine — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V18_C_LIVE_ELIGIBLE_UNIVERSE_ENGINE"
LANE = "V18-C"
LANE_NAME = "LIVE_ELIGIBLE_UNIVERSE_ENGINE"
BRANCH = "feature/v18-live-eligible-universe"
BASE_COMMIT = "324e52f0573d7e3ad32feb2968274a52b8d8da75"
CAMPAIGN_ID = "v18_c_eligible_universe"
RANDOM_SEED = 20260806

# Universe membership classes (fail-closed).
UNIVERSE_CLASSES: tuple[str, ...] = (
    "ELIGIBLE",
    "OBSERVE_ONLY",
    "LOW_LIQUIDITY",
    "WIDE_SPREAD",
    "INSUFFICIENT_HISTORY",
    "NEW_LISTING",
    "DELISTING_RISK",
    "DATA_DEGRADED",
    "COST_INFEASIBLE",
    "MARKET_HALTED",
    "LICENSE_BLOCKED",
    "UNAVAILABLE",
)

# Severity: higher = worse. First matching worst class wins.
CLASS_SEVERITY: dict[str, int] = {
    "ELIGIBLE": 0,
    "OBSERVE_ONLY": 1,
    "LOW_LIQUIDITY": 2,
    "WIDE_SPREAD": 3,
    "INSUFFICIENT_HISTORY": 4,
    "NEW_LISTING": 5,
    "DELISTING_RISK": 6,
    "DATA_DEGRADED": 7,
    "COST_INFEASIBLE": 8,
    "MARKET_HALTED": 9,
    "LICENSE_BLOCKED": 10,
    "UNAVAILABLE": 11,
}

# Gate identifiers (founder-required).
GATES: tuple[str, ...] = (
    "trading_status",
    "listing_age",
    "turnover_24h",
    "trade_frequency",
    "spread",
    "book_depth",
    "funding_availability",
    "oi_availability",
    "data_completeness",
    "data_trust",
    "contract_specs",
    "delisting_state",
    "cost_feasibility",
)

FUNNEL_KEYS: tuple[str, ...] = (
    "total_exchange_contracts",
    "catalog_valid_contracts",
    "data_available_contracts",
    "liquidity_pass_contracts",
    "cost_pass_contracts",
    "eligible_contracts",
    "observe_only_contracts",
    "blocked_contracts",
)

# Thresholds (USDT linear defaults; fail-closed when metrics missing).
MIN_LISTING_AGE_DAYS = 7.0
MIN_HISTORY_BARS = 96  # ~24h of 15m bars
MIN_TURNOVER_24H_USDT = 5_000_000.0
MIN_TRADE_COUNT_24H = 5_000
MAX_SPREAD_BPS = 25.0
MIN_BOOK_DEPTH_USDT = 50_000.0
MIN_OI_VALUE_USDT = 1_000_000.0
MAX_ROUND_TRIP_COST_BPS = 40.0
MIN_DATA_COMPLETENESS = 0.80
MIN_TRUST_FOR_ELIGIBLE = frozenset({"TRUSTED", "USABLE_WITH_LIMITS"})
TRUST_DEGRADED = frozenset({"DEGRADED", "STALE", "CONFLICTED"})
TRUST_LICENSE_BLOCK = frozenset({"LICENSE_BLOCKED"})
TRUST_UNAVAILABLE = frozenset({"UNAVAILABLE"})
OBSERVE_TRUST = frozenset({"USABLE_WITH_LIMITS"})

TRADING_OK_STATUSES = frozenset({"Trading", "TRADING", "trading"})
DELISTING_STATUSES = frozenset(
    {
        "PreDelisting",
        "Settling",
        "Closed",
        "DELISTING",
        "PRE_DELISTING",
        "SETTLING",
        "CLOSED",
    }
)
HALTED_STATUSES = frozenset(
    {
        "Halt",
        "HALT",
        "Suspended",
        "SUSPENDED",
        "Delivering",
    }
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_eligible_universe",
    "tools/research/eligible_universe",
    "tests/eligible_universe",
)

HARD_BANS: frozenset[str] = frozenset(
    {
        "no_exchange_write",
        "no_mainnet",
        "no_demo",
        "no_real_money",
        "no_pr26_merge",
        "no_pr27_merge",
        "no_acceleration_report_edit",
        "no_archive_rebuild",
        "no_unknown_defaults_to_eligible",
        "no_hardcoded_fake_funnel",
    }
)

FORBIDDEN_ARTIFACT_SUFFIXES: tuple[str, ...] = (
    "acceleration_report",
    "NEXUS_FINAL_ACCELERATION_REPORT",
    "NEXUS_ALL_AGENTS",
    "lane_status.json",
    "v18_c_status.json",
)

BANNED_CLAIM_FRAGMENTS: tuple[str, ...] = (
    "15y complete",
    "all-exchange history",
    "full training set",
    "strategy validation PASS",
    "qualification_ready",
)
