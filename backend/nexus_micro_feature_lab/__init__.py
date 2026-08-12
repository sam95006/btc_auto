"""V13-E Microstructure Feature Lab — descriptive feature extraction surface.

Hard bans: no predictive edge claims, no silent seal/modify of old raw partitions,
no Event Study, no Demo/exchange, no PR27 merge.
"""
from __future__ import annotations

from backend.nexus_micro_feature_lab.catalog import feature_catalog, require_feature
from backend.nexus_micro_feature_lab.constants import (
    FEATURE_IDS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    SCHEMA,
)
from backend.nexus_micro_feature_lab.extractors import (
    extract_all_features,
    extract_bundle_from_capture,
)
from backend.nexus_micro_feature_lab.fixtures import build_synthetic_capture
from backend.nexus_micro_feature_lab.forensic_ro import (
    ForensicWriteAttemptError,
    forensic_campaign_probe,
    refuse_write,
)
from backend.nexus_micro_feature_lab.replay import (
    fingerprint_bundle,
    prove_pit_excludes_future,
    run_extraction_once,
    verify_deterministic_replay,
)

__all__ = [
    "FEATURE_IDS",
    "HARD_BANS",
    "LANE",
    "LANE_NAME",
    "SCHEMA",
    "ForensicWriteAttemptError",
    "build_synthetic_capture",
    "extract_all_features",
    "extract_bundle_from_capture",
    "feature_catalog",
    "fingerprint_bundle",
    "forensic_campaign_probe",
    "prove_pit_excludes_future",
    "refuse_write",
    "require_feature",
    "run_extraction_once",
    "verify_deterministic_replay",
]
