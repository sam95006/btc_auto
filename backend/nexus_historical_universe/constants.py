"""V17-E Historical Universe and Survivorship Control — constants."""
from __future__ import annotations

SCHEMA = "v17_e_historical_universe_survivorship_v1"
SCHEMA_VERSION = 1
LANE = "V17-E"
LANE_NAME = "HISTORICAL_UNIVERSE_AND_SURVIVORSHIP_CONTROL"
PROGRAM_ID = "NEXUS_V17_HISTORICAL_UNIVERSE_SURVIVORSHIP"
BRANCH = "feature/v17-historical-universe-survivorship"
BASE_COMMIT = "66a0f7827d5709fc09bc8c7495e93a4089eb28de"

PASS_RECOMMENDATION = "NEXUS_V17_HISTORICAL_UNIVERSE_SURVIVORSHIP_PASS"
FAIL_RECOMMENDATION = "NEXUS_V17_HISTORICAL_UNIVERSE_SURVIVORSHIP_FAIL"
BLOCKED_RECOMMENDATION = "NEXUS_V17_HISTORICAL_UNIVERSE_SURVIVORSHIP_SURVIVORS_REMAIN"

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_historical_universe/",
    "tools/historical_universe/",
    "tests/historical_universe/",
    "artifacts/readiness/immutable/v17_historical_universe/",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "deploy/",
    "G:/",
    "PR26",
    "PR27",
    "acceleration_report",
)

HARD_BANS: tuple[str, ...] = (
    "no_today_survivors_for_whole_history",
    "no_pre_listing_data",
    "no_ignoring_delistings",
    "no_current_liquidity_substitution",
    "no_exchange_write",
    "no_mainnet",
    "no_real_money",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
)

ATTACK_IDS: tuple[str, ...] = (
    "today_survivors_for_history",
    "pre_listing_data",
    "ignore_delistings",
    "current_liquidity_substitution",
)

FIXTURE_IDS: tuple[str, ...] = (
    "multi_era_membership",
    "listing_delisting_events",
    "contract_spec_timeline",
    "liquidity_pit_binding",
    "data_completeness_gate",
)

# Tradable statuses that may enter eligible universe when other gates pass.
TRADABLE_STATUSES: frozenset[str] = frozenset({"Trading"})
EXCLUDED_STATUSES: frozenset[str] = frozenset(
    {"PreLaunch", "Settling", "Delivering", "Closed", "Delisted"}
)

DEFAULT_MIN_LIQUIDITY_SCORE = 0.05
DEFAULT_MIN_DATA_COMPLETENESS = 0.50

EVIDENCE_CLASS = "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
LABEL = "HISTORICAL_UNIVERSE_SURVIVORSHIP_CONTROL_NOT_REAL_TRADING"
EXECUTION_MODE = "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE"

ARTIFACT_REL = "artifacts/readiness/immutable/v17_historical_universe"
EVIDENCE_PATH = r"D:\NEXUS_RUNTIME\evidence_coordinator\v17_e_survivorship.json"
WORKTREE_PATH = r"D:\NEXUS_RUNTIME\worktrees\v17_e_survivorship"

# Canonical fixture eras (ms UTC)
ERA_2024_06_01_MS = 1_717_200_000_000
ERA_2024_12_01_MS = 1_733_020_800_000
ERA_2025_03_01_MS = 1_740_787_200_000
TODAY_SURVIVOR_ERA_MS = 1_754_438_400_000  # 2025-08-06 approx "today" fixture era
