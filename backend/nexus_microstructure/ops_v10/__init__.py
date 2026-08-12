"""Microstructure Operations V10 — campaign ops package (dry-run / controller first).

Hard bans: no Event Study start, no strategy generation, no exchange write.
"""
from __future__ import annotations

from backend.nexus_microstructure.ops_v10.constants import (
    DEFAULT_PREVIOUS_CAMPAIGN_ID,
    GIB,
    MIN_FREE_DISK_BYTES_FOR_NEW_SEGMENT,
    SCHEMA,
)
from backend.nexus_microstructure.ops_v10.finalizer_bridge import FinalizerIntegrationV10
from backend.nexus_microstructure.ops_v10.gates import CaptureStartGatesV10, evaluate_capture_start_gates
from backend.nexus_microstructure.ops_v10.integrity_scoring import score_campaign_integrity
from backend.nexus_microstructure.ops_v10.registry import CampaignRegistryV10
from backend.nexus_microstructure.ops_v10.retention import retention_dry_run_v10
from backend.nexus_microstructure.ops_v10.resume import BoundedResumeController
from backend.nexus_microstructure.ops_v10.safe_stop import AutomaticSafeStop

__all__ = [
    "SCHEMA",
    "GIB",
    "MIN_FREE_DISK_BYTES_FOR_NEW_SEGMENT",
    "DEFAULT_PREVIOUS_CAMPAIGN_ID",
    "CampaignRegistryV10",
    "BoundedResumeController",
    "AutomaticSafeStop",
    "FinalizerIntegrationV10",
    "CaptureStartGatesV10",
    "evaluate_capture_start_gates",
    "retention_dry_run_v10",
    "score_campaign_integrity",
]
