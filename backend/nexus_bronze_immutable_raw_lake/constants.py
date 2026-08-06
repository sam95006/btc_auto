"""V17-B Bronze Immutable Raw Data Lake — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v17_b_bronze_immutable_raw_lake_v1"
SCHEMA_RECORD = "v17_b_bronze_record_v1"
SCHEMA_MANIFEST = "v17_b_bronze_manifest_v1"
SCHEMA_LINEAGE = "v17_b_bronze_lineage_v1"
SCHEMA_CAMPAIGN = "v17_b_bronze_campaign_v1"
SCHEMA_VERSION = "1.0.0"
PACKAGE = "backend.nexus_bronze_immutable_raw_lake"
LANE = "V17-B"
LANE_NAME = "BRONZE_IMMUTABLE_RAW_LAKE"
BRANCH = "feature/v17-bronze-immutable-raw-lake"
ARTIFACT_REL = "artifacts/readiness/immutable/v17_bronze_immutable_raw_lake"
BASE_COMMIT = "66a0f7827d5709fc09bc8c7495e93a4089eb28de"
PROGRAM_ID = "NEXUS_V17_DATA_MOAT_BRONZE_IMMUTABLE_RAW_LAKE"

# Required append-only Bronze record fields (Founder contract).
BRONZE_REQUIRED_FIELDS: tuple[str, ...] = (
    "exchange_timestamp",
    "received_timestamp",
    "ingested_timestamp",
    "source_id",
    "symbol_original",
    "payload",
    "content_hash",
    "partition_hash",
    "schema_version",
    "compression",
    "license_reference",
)

COMPRESSION_NONE = "none"
COMPRESSION_GZIP = "gzip"
ALLOWED_COMPRESSIONS: frozenset[str] = frozenset({COMPRESSION_NONE, COMPRESSION_GZIP})

# Data classification — this round is fixture / bounded sample ONLY.
CLASSIFICATION_FIXTURE = "FIXTURE"
CLASSIFICATION_BOUNDED_OFFICIAL_SAMPLE = "BOUNDED_OFFICIAL_SAMPLE"
CLASSIFICATION_FULL_HISTORY = "FULL_HISTORY"  # refused this round
ALLOWED_INGEST_CLASSIFICATIONS: frozenset[str] = frozenset(
    {CLASSIFICATION_FIXTURE, CLASSIFICATION_BOUNDED_OFFICIAL_SAMPLE}
)

DEFAULT_MAX_DISK_BYTES = 8 * 1024 * 1024  # 8 MiB bound for fixture round
DEFAULT_LICENSE_REFERENCE = "in_repo_fixture_sample_v17b_not_exchange_redistribution"

HARD_BANS: tuple[str, ...] = (
    "no_real_money",
    "no_mainnet",
    "no_exchange_write",
    "no_historical_rewrite",
    "no_ai_mutate_raw_payload",
    "no_non_utc_timestamps",
    "no_claim_15y_history_downloaded",
    "no_full_history_ingest_this_round",
    "no_oos",
    "no_walkforward",
    "no_fabricated_ai_learning",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_status_json_lane_artifact",
    "no_acceleration_report_edit",
    "no_auto_integrate",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_bronze_immutable_raw_lake/",
    "tests/bronze_immutable_raw_lake/",
    "tools/research/bronze_immutable_raw_lake/",
    ARTIFACT_REL + "/",
)

HARD_BAN_FLAGS: dict[str, bool] = {
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "pr26_merged": False,
    "pr27_merged": False,
    "demo": False,
    "ai_may_mutate_raw_payload": False,
    "historical_rewrite_allowed": False,
    "full_15y_history_claimed": False,
}
