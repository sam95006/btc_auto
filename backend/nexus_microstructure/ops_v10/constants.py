"""Constants for Microstructure Operations V10."""
from __future__ import annotations

SCHEMA = "microstructure_operations_v10"
GIB = 1024**3
MIN_FREE_DISK_BYTES_FOR_NEW_SEGMENT = 30 * GIB
DEFAULT_PREVIOUS_CAMPAIGN_ID = "ms_accum_v7_bounded_24h"
DEFAULT_REAL_FINALIZER_ARTIFACT_DIR = (
    "artifacts/readiness/immutable/microstructure_campaign_finalizer_v1_real_ms_accum_v7"
)
EVENT_STUDY_MUST_REMAIN = "NOT_READY"
