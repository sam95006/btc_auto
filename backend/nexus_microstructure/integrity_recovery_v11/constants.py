"""V11 microstructure integrity recovery — constants and classification taxonomy."""
from __future__ import annotations

SCHEMA = "microstructure_integrity_recovery_v11"

CLASSIFICATIONS = (
    "ACTUAL_DATA_CORRUPTION",
    "EXPECTED_OPEN_TAIL",
    "MIGRATION_ARTIFACT",
    "MANIFEST_BUG",
    "FINALIZER_FALSE_POSITIVE",
    "LINKAGE_SEMANTICS_BUG",
    "UNKNOWN_REQUIRES_MORE_EVIDENCE",
)

# Campaign under forensic review (read-only).
REFERENCE_CAMPAIGN_ID = "ms_accum_v7_bounded_24h"
REFERENCE_FINALIZER_ARTIFACT_DIR = (
    "artifacts/readiness/immutable/microstructure_campaign_finalizer_v1_real_ms_accum_v7"
)

# Failure counters reported by V1 finalizer for the real campaign (capped lists noted).
REPORTED_CHECKSUM_FAILURE_COUNT = 50  # capped failure list; all TRUNCATED_OR_INCOMPLETE
REPORTED_TRUNCATED_TAIL_COUNT = 113
REPORTED_CROSS_PARTITION_LINK_FAILURE_COUNT = 167
