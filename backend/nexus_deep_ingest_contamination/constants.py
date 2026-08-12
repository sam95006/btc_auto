"""V17 deep engineering — ingest recovery + dataset contamination constants."""
from __future__ import annotations

SCHEMA = "v17_deep_ingest_contamination_v1"
SCHEMA_CAMPAIGN = "v17_deep_ingest_contamination_campaign_v1"
SCHEMA_REDTEAM = "v17_deep_ingest_contamination_redteam_v1"
LANE = "V17-DEEP-INGEST"
LANE_NAME = "INGEST_RECOVERY_AND_DATASET_CONTAMINATION"
BRANCH = "feature/v17-deep-ingest-contamination"
PROGRAM_ID = "NEXUS_V17_DEEP_INGEST_CONTAMINATION"
BASE_SHA = "a43317e2f85afde75e850ffa4ef465c834fd7a6a"
ARTIFACT_REL = "artifacts/readiness/immutable/v17_deep_ingest_contamination"
PACKAGE = "backend.nexus_deep_ingest_contamination"

# Bounded resource limits for fixture-round smoke profiling (NOT 15y history).
BOUNDED_MAX_DISK_BYTES = 4 * 1024 * 1024  # 4 MiB
BOUNDED_MAX_MEMORY_BYTES = 32 * 1024 * 1024  # 32 MiB documented ceiling
BOUNDED_MAX_ARCHIVE_ENTRIES = 64
BOUNDED_MAX_INGEST_BATCH = 32

# Provider failover fixture identities (no live network).
PRIMARY_PROVIDER = "fixture_primary"
SECONDARY_PROVIDER = "fixture_secondary"
RATE_LIMIT_STATUS = 429
OUTAGE_STATUS = 503

HARD_BANS: tuple[str, ...] = (
    "no_real_money",
    "no_mainnet",
    "no_exchange_write",
    "no_formal_walk_forward",
    "no_untouched_oos",
    "no_claim_15y_history_downloaded",
    "no_full_history_ingest_this_round",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "no_auto_integrate",
    "no_reserved_split_training",
    "no_lookahead_contamination",
    "no_cross_split_leak",
    "no_silent_corrupt_resume",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_deep_ingest_contamination/",
    "tests/deep_ingest_contamination/",
    "tools/research/deep_ingest_contamination/",
    ARTIFACT_REL + "/",
)

NON_CLAIMS: tuple[str, ...] = (
    "No formal Walk-Forward executed",
    "No OOS consumption or sealed OOS metrics claimed",
    "No 15y historical data download claimed",
    "No exchange/mainnet/real-money capability",
    "Synthetic fixtures only — not live market ingestion",
    "Bounded memory/disk smoke only — not production capacity proof",
)

EXPECTED_CONTAMINATION_ATTACKS = 10
EXPECTED_MIN_TESTS = 12

COVERAGE_AREAS: tuple[str, ...] = (
    "corrupt_archive_recovery",
    "duplicate_dataset_ingestion",
    "revision_conflict_testing",
    "dataset_split_contamination_attacks",
    "api_rate_limit_and_provider_outage_failover",
    "bounded_memory_disk_profiling_smoke",
)
