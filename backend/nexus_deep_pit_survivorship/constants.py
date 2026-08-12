"""V17 deep engineering — PIT / survivorship / symbol-collision constants."""
from __future__ import annotations

SCHEMA = "v17_deep_pit_survivorship_v1"
SCHEMA_CAMPAIGN = "v17_deep_pit_survivorship_campaign_v1"
SCHEMA_REDTEAM = "v17_deep_pit_survivorship_redteam_v1"
LANE = "V17-DEEP-PIT-SURVIVORSHIP"
LANE_NAME = "PIT_SURVIVORSHIP_SYMBOL_COLLISION_ATTACKS"
BRANCH = "feature/v17-deep-pit-survivorship-attacks"
PROGRAM_ID = "NEXUS_V17_DEEP_PIT_SURVIVORSHIP"
BASE_SHA = "a43317e2f85afde75e850ffa4ef465c834fd7a6a"
ARTIFACT_REL = "artifacts/readiness/immutable/v17_deep_pit_survivorship"
PACKAGE = "backend.nexus_deep_pit_survivorship"
EVIDENCE_PATH = r"D:\NEXUS_RUNTIME\evidence_coordinator\v17_deep_pit_survivorship.json"
WORKTREE_PATH = r"D:\NEXUS_RUNTIME\worktrees\v17_deep_pit_survivorship"

HARD_BANS: tuple[str, ...] = (
    "no_real_money",
    "no_mainnet",
    "no_exchange_write",
    "no_formal_walk_forward",
    "no_untouched_oos",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "no_auto_integrate",
    "no_future_leakage",
    "no_research_query_without_as_known_at",
    "no_today_revision_for_past_backtest",
    "no_today_survivors_for_whole_history",
    "no_pre_listing_data",
    "no_ignoring_delistings",
    "no_current_liquidity_substitution",
    "no_collapse_cross_exchange_symbols",
    "no_collapse_spot_perp_identity",
    "no_symbol_only_identity",
    "no_tz_local_as_known_at",
    "no_leap_second_aware_claim",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_deep_pit_survivorship/",
    "tests/deep_pit_survivorship/",
    "tools/research/run_deep_pit_survivorship.py",
    ARTIFACT_REL + "/",
)

NON_CLAIMS: tuple[str, ...] = (
    "No formal Walk-Forward executed",
    "No OOS consumption or sealed OOS metrics claimed",
    "No exchange/mainnet/real-money capability",
    "Synthetic fixtures only — not live market ingestion",
    "Leap-second handling is UTC continuous epoch-ms (no leap-second table)",
)

COVERAGE_AREAS: tuple[str, ...] = (
    "property_mutation_as_known_at_revision",
    "timestamp_boundary_dst_utc",
    "cross_exchange_symbol_collision",
    "listing_delisting_survivorship",
    "future_leakage_redteam_expansion",
)

# Property / mutation campaign sizing (deterministic seed).
PROPERTY_SEED = 17_170_001
PROPERTY_CASE_COUNT = 64
MUTATION_CASE_COUNT = 48

# UTC continuous ms — leap seconds are NOT inserted into the timeline.
LEAP_SECOND_POLICY = "UTC_CONTINUOUS_EPOCH_MS_NO_LEAP_SECOND_TABLE"

EXPECTED_MIN_NEW_TESTS = 18
EXPECTED_EXPANDED_LEAKAGE_ATTACKS = 10
