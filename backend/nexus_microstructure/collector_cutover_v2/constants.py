"""Collector Cutover V2 — constants and retained prior-campaign classifications."""
from __future__ import annotations

SCHEMA = "microstructure_collector_cutover_v2"

# Frozen forensic counts from V11 integrity recovery (read-only; do not mutate raw).
RETAINED_CLASSIFICATION_COUNTS = {
    "ACTUAL_DATA_CORRUPTION": 0,
    "EXPECTED_OPEN_TAIL": 113,
    "MIGRATION_ARTIFACT": 113,
    "MANIFEST_BUG": 43,
    "FINALIZER_FALSE_POSITIVE": 113,
    "LINKAGE_SEMANTICS_BUG": 113,
    "UNKNOWN_REQUIRES_MORE_EVIDENCE": 0,
}

RETAINED_PRIMARY_CLASSIFICATION_COUNTS = {
    "ACTUAL_DATA_CORRUPTION": 0,
    "EXPECTED_OPEN_TAIL": 113,
    "MIGRATION_ARTIFACT": 0,
    "MANIFEST_BUG": 43,
    "FINALIZER_FALSE_POSITIVE": 0,
    "LINKAGE_SEMANTICS_BUG": 0,
    "UNKNOWN_REQUIRES_MORE_EVIDENCE": 0,
}

REFERENCE_CAMPAIGN_ID = "ms_accum_v7_bounded_24h"

EVENT_STUDY_STATUS = "NOT_READY"

# R2 High residuals in collector scope must be FIXED or hard-guarded — never silent accept.
R2_HIGH_DISPOSITIONS = {
    # Durability ledger (Lane C) — out of collector write path; hard-block production.
    "R2-C-003": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",
    "R2-C-004": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",
    "R2-C-006": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",
    "R2-C-007": "DEFERRED_NON_PRODUCTION_WITH_HARD_BLOCK",
    # Collector partition path — FIXED in Cutover V2.
    "R2-D-001": "FIXED",  # exclusive partition identity (O_EXCL + conflict registry)
    "R2-D-002": "FIXED",  # orphan .open classified + V2 seal order
    "R2-D-003": "FIXED",  # persistent clock + refuse backward hour rotation
    "R2-D-004": "FIXED",  # interrupted finalize authority signal
    "R2-D-005": "FIXED",  # migration/export refuses *.jsonl.gz.open trees
}

CLOCK_WATERMARK_FILENAME = "collector_clock_watermark_v2.json"
SESSION_LINKAGE_FILENAME = "collector_session_linkage_v2.json"
OPEN_MARKER_SUFFIX = ".open"
SEAL_STATE_SUFFIX = ".seal_state"
