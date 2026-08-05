"""V15-A Real Historical Development Data Foundation — constants."""
from __future__ import annotations

SCHEMA = "FOUNDER_V15_A_DEV_DATA_FOUNDATION"
SCHEMA_VERSION = 1
RECORD_SCHEMA = "nexus_pit_dev_data_record_v15_a"
PARTITION_SCHEMA = "nexus_pit_time_partition_v15_a"
INVENTORY_SCHEMA = "nexus_pit_source_inventory_v15_a"
LINEAGE_SCHEMA = "nexus_pit_dev_data_lineage_v15_a"
LANE = "V15-A"
LANE_NAME = "REAL_HISTORICAL_DEVELOPMENT_DATA_FOUNDATION"
BRANCH = "feature/v15-real-development-data-foundation"
BASE_COMMIT = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"
PROGRAM_ID = "NEXUS_V15_A_REAL_DEVELOPMENT_DATA_FOUNDATION"

# Canonical research windows (aligned with closed_historical_registry / H4-H5).
HOLDOUT_CONSUMED_START_MS = 1_720_863_000_000
HOLDOUT_CONSUMED_END_MS = 1_736_415_000_000
DEV_START_MS = 1_739_007_000_000
DEV_END_MS = 1_785_663_000_000
SEPTEMBER_OOS_START_MS = 1_785_663_000_001
SEPTEMBER_OOS_END_MS = 1_789_551_000_000

# Partition categories — OOS never consumed by this lane.
PARTITION_CATEGORIES = (
    "DEVELOPMENT",
    "VALIDATION_PLANNING",
    "OOS_RESERVED",
    "OOS_UNTOUCHED",
)

AVAILABILITY_STATES = (
    "AVAILABLE",
    "MISSING",
    "STALE",
    "UNSUPPORTED",
    "METADATA_ONLY",
    "CONSUMED_FORBIDDEN",
    "RESERVED_UNTOUCHED",
)

HARD_BANS = {
    "pr26_merge": False,
    "pr27_merge": False,
    "deploy": False,
    "formal_walk_forward": False,
    "oos_execution": False,
    "oos_consumption": False,
    "demo_orders": False,
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "fabricated_edge": False,
    "invented_history": False,
    "auto_integration": False,
    "human_facing_v15_status_json": False,
}

HARD_BAN_FLAGS = {
    "read_only": True,
    "exchange_write": False,
    "demo_order": False,
    "shadow_order": False,
    "oos_consumed": False,
    "oos_executed": False,
    "formal_walk_forward_executed": False,
    "mainnet": False,
    "real_money": False,
    "profitability_claim": False,
    "learning_claim": False,
    "fabricated_edge": False,
    "invented_history": False,
    "auto_integration": False,
}

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_dev_data_foundation/",
    "tools/research/dev_data_foundation/",
    "tests/dev_data_foundation/",
    "artifacts/readiness/immutable/v15_dev_data_foundation/",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "deploy/",
    "G:/",
    "PR26",
    "PR27",
)

# Artifact names intentionally avoid v15_*_status.json (Founder report rule).
ART_REL = "artifacts/readiness/immutable/v15_dev_data_foundation"
FORBIDDEN_STATUS_GLOB = "v15_*_status.json"

LABEL = "DEVELOPMENT_DATA_FOUNDATION_NOT_QUALIFICATION"
EVIDENCE_CLASS = "PIT_SOURCE_INVENTORY_NOT_STRATEGY_EDGE"
EXECUTION_MODE = "READ_ONLY_NO_EXCHANGE_WRITE_NO_OOS"

PASS_RECOMMENDATION = "NEXUS_V15_A_DEV_DATA_FOUNDATION_PASS"
FAIL_RECOMMENDATION = "NEXUS_V15_A_DEV_DATA_FOUNDATION_CRITICAL_FINDINGS"

STRUCTURAL_BLOCKERS: tuple[str, ...] = (
    "raw_historical_bars_gitignored_or_absent",
    "qualification_ready_count_must_remain_0",
    "oos_executed_must_remain_false",
    "formal_walk_forward_must_remain_false",
    "PR26_unmerged",
    "PR27_unmerged",
    "auto_integration_forbidden",
    "no_fabricated_strategy_edge",
)

# In-repo legally accessible public/sanitized historical sources.
IN_REPO_SOURCE_SPECS: tuple[dict[str, str], ...] = (
    {
        "source_id": "pit_universe_fixture_index",
        "kind": "sanitized_pit_fixture",
        "path": "backend/nexus_market_discovery/fixtures/index.json",
        "legal_basis": "in_repo_sanitized_fixture",
    },
    {
        "source_id": "pit_universe_era_2024_06_01",
        "kind": "sanitized_pit_fixture",
        "path": "backend/nexus_market_discovery/fixtures/era_2024_06_01.json",
        "legal_basis": "in_repo_sanitized_fixture",
    },
    {
        "source_id": "pit_universe_era_2024_12_01",
        "kind": "sanitized_pit_fixture",
        "path": "backend/nexus_market_discovery/fixtures/era_2024_12_01.json",
        "legal_basis": "in_repo_sanitized_fixture",
    },
    {
        "source_id": "pit_universe_era_2025_03_01",
        "kind": "sanitized_pit_fixture",
        "path": "backend/nexus_market_discovery/fixtures/era_2025_03_01.json",
        "legal_basis": "in_repo_sanitized_fixture",
    },
    {
        "source_id": "real_shadow_kline_sample",
        "kind": "public_ro_fixture_sample",
        "path": "backend/nexus_real_shadow/fixtures/kline.json",
        "legal_basis": "in_repo_public_api_shape_fixture",
    },
    {
        "source_id": "real_shadow_funding_sample",
        "kind": "public_ro_fixture_sample",
        "path": "backend/nexus_real_shadow/fixtures/funding.json",
        "legal_basis": "in_repo_public_api_shape_fixture",
    },
    {
        "source_id": "real_shadow_open_interest_sample",
        "kind": "public_ro_fixture_sample",
        "path": "backend/nexus_real_shadow/fixtures/open_interest.json",
        "legal_basis": "in_repo_public_api_shape_fixture",
    },
    {
        "source_id": "real_shadow_instruments_info",
        "kind": "public_ro_fixture_sample",
        "path": "backend/nexus_real_shadow/fixtures/instruments_info.json",
        "legal_basis": "in_repo_public_api_shape_fixture",
    },
    {
        "source_id": "h5_historical_data_manifest",
        "kind": "historical_manifest_metadata",
        "path": "artifacts/readiness/immutable/dynamic_universe_ai_learning_h5_v1/historical_data_manifest.json",
        "legal_basis": "in_repo_research_manifest_metadata_only",
    },
    {
        "source_id": "consumed_failed_oos_holdout",
        "kind": "consumed_holdout_registry",
        "path": "artifacts/readiness/immutable/consumed_failed_oos/consumed_oos_holdout.json",
        "legal_basis": "in_repo_immutable_consumed_marker",
    },
)

# Documented read-only public endpoints (probe availability; never invent history).
PUBLIC_RO_ENDPOINTS: tuple[dict[str, str], ...] = (
    {
        "source_id": "bybit_public_kline_v5",
        "kind": "read_only_public_endpoint",
        "url": "https://api.bybit.com/v5/market/kline",
        "legal_basis": "exchange_public_market_data_readonly",
    },
    {
        "source_id": "bybit_public_instruments_info_v5",
        "kind": "read_only_public_endpoint",
        "url": "https://api.bybit.com/v5/market/instruments-info",
        "legal_basis": "exchange_public_market_data_readonly",
    },
)
