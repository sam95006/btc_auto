"""V18-B Incremental Backfill + Live Ingest — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v18_b_incremental_backfill_live_ingest_v1"
SCHEMA_CAMPAIGN = "v18_b_incremental_backfill_live_ingest_campaign_v1"
SCHEMA_MANIFEST = "v18_b_date_partition_manifest_v1"
SCHEMA_CHECKPOINT = "v18_b_ingest_resume_checkpoint_v1"
SCHEMA_COUNTERS = "v18_b_acceptance_counters_v1"
SCHEMA_VERSION = "1.0.0"
PACKAGE = "backend.nexus_incremental_backfill_live_ingest"
LANE = "V18-B"
LANE_NAME = "INCREMENTAL_BACKFILL_AND_LIVE_INGEST"
BRANCH = "feature/v18-incremental-backfill-live-ingest"
BASE_COMMIT = "324e52f0573d7e3ad32feb2968274a52b8d8da75"
PROGRAM_ID = "NEXUS_V18_INCREMENTAL_BACKFILL_LIVE_INGEST"
ARTIFACT_REL = "artifacts/readiness/immutable/v18_incremental_backfill_live_ingest"

# Priority validation symbols — NOT a hard max of 4; dynamic universe later.
PRIORITY_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "PEPEUSDT",
)

# Data classes (Founder contract).
DATA_CLASS_LIVE_READ_ONLY = "LIVE_READ_ONLY"
DATA_CLASS_OFFICIAL_HISTORICAL_SAMPLE = "OFFICIAL_HISTORICAL_SAMPLE"
DATA_CLASS_FIXTURE = "FIXTURE"
DATA_CLASS_STALE = "STALE"
DATA_CLASS_DEGRADED = "DEGRADED"
DATA_CLASS_UNAVAILABLE = "UNAVAILABLE"

INGESTIBLE_DATA_CLASSES: frozenset[str] = frozenset(
    {
        DATA_CLASS_LIVE_READ_ONLY,
        DATA_CLASS_OFFICIAL_HISTORICAL_SAMPLE,
        DATA_CLASS_FIXTURE,
    }
)

NON_INGEST_DATA_CLASSES: frozenset[str] = frozenset(
    {
        DATA_CLASS_STALE,
        DATA_CLASS_DEGRADED,
        DATA_CLASS_UNAVAILABLE,
    }
)

ALL_DATA_CLASSES: frozenset[str] = INGESTIBLE_DATA_CLASSES | NON_INGEST_DATA_CLASSES

# Bounded sample windows allowed this round (days).
ALLOWED_BACKFILL_WINDOWS_DAYS: frozenset[int] = frozenset({7, 30, 90})
DEFAULT_BACKFILL_WINDOW_DAYS = 7

# Map V18 data class → V17 Bronze ingest classification.
BRONZE_CLASS_MAP: dict[str, str] = {
    DATA_CLASS_FIXTURE: "FIXTURE",
    DATA_CLASS_OFFICIAL_HISTORICAL_SAMPLE: "BOUNDED_OFFICIAL_SAMPLE",
    DATA_CLASS_LIVE_READ_ONLY: "BOUNDED_OFFICIAL_SAMPLE",
}

DEFAULT_LICENSE_REFERENCE = "v18b_licensed_official_or_fixture_sample_not_redistributed_bulk"
DEFAULT_SOURCE_ID = "binance_spot_klines_1m"
DEFAULT_MAX_DISK_BYTES = 8 * 1024 * 1024  # 8 MiB bound
DEFAULT_RETENTION_DAYS = 90
DEFAULT_RATE_LIMIT_WEIGHT = 1200

# Acceptance counters that MUST remain zero.
ACCEPTANCE_ZERO_COUNTERS: tuple[str, ...] = (
    "raw_rewrite_count",
    "duplicate_unresolved_count",
    "future_timestamp_accept_count",
    "unlicensed_ingest_count",
    "silent_gap_fill_count",
)

HARD_BANS: tuple[str, ...] = (
    "no_real_money",
    "no_mainnet",
    "no_exchange_write",
    "no_demo",
    "no_historical_rewrite",
    "no_silent_gap_fill",
    "no_unlicensed_ingest",
    "no_future_timestamp_accept",
    "no_claim_15y_complete",
    "no_claim_all_exchange_history",
    "no_claim_full_training_set",
    "no_claim_strategy_validation_pass",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "no_auto_integrate",
    "no_report_archive_rebuild",
)

BANNED_CLAIMS: tuple[str, ...] = (
    "15y_complete",
    "all_exchange_history",
    "full_training_set",
    "strategy_validation_PASS",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_incremental_backfill_live_ingest/",
    "tests/incremental_backfill_live_ingest/",
    "tools/research/incremental_backfill_live_ingest/",
    ARTIFACT_REL + "/",
)

NON_CLAIMS: tuple[str, ...] = (
    "No 15y complete history claimed",
    "No all-exchange history claimed",
    "No full training set claimed",
    "No strategy validation PASS claimed",
    "Bounded 7/30/90d official sample / fixture / live-append only",
    "No exchange write / demo / mainnet / real-money",
    "No PR26 / PR27 merge",
    "No acceleration report / archive rebuild",
)

CAPABILITIES: tuple[str, ...] = (
    "incremental_backfill",
    "date_partitioned_manifest",
    "checkpoint",
    "resume",
    "checksum",
    "dedupe",
    "corrupt_quarantine",
    "rate_limit_pause",
    "disk_quota",
    "retention",
    "license_binding",
    "partial_failure_recovery",
    "live_append",
    "bronze_silver_pit_wire",
)
