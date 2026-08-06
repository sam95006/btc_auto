"""V17-B Bronze Immutable Raw Data Lake — append-only fixture/bounded-sample lake."""
from __future__ import annotations

from backend.nexus_bronze_immutable_raw_lake.campaign import run_campaign
from backend.nexus_bronze_immutable_raw_lake.constants import (
    ARTIFACT_REL,
    BRANCH,
    BRONZE_REQUIRED_FIELDS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_bronze_immutable_raw_lake.fixtures import (
    all_bounded_ingest_batches,
    sample_inventory,
)
from backend.nexus_bronze_immutable_raw_lake.lake import BronzeLake, DiskBudgetExceeded
from backend.nexus_bronze_immutable_raw_lake.records import (
    attempt_ai_mutate_payload,
    build_bronze_record,
    verify_bronze_record,
)

__all__ = [
    "SCHEMA",
    "SCHEMA_VERSION",
    "LANE",
    "LANE_NAME",
    "BRANCH",
    "OWNED_PATHS",
    "HARD_BANS",
    "ARTIFACT_REL",
    "BRONZE_REQUIRED_FIELDS",
    "BronzeLake",
    "DiskBudgetExceeded",
    "build_bronze_record",
    "verify_bronze_record",
    "attempt_ai_mutate_payload",
    "all_bounded_ingest_batches",
    "sample_inventory",
    "run_campaign",
]
