"""V17 deep engineering — license enforcement + public inference attacks.

Coverage:
1. License enforcement (restricted statuses must not leak to member UI as Live)
2. Public inference leakage (multi-query reverse engineering) — survivors=0
3. Schema fuzzing on public DTOs / projection allow-list
4. Feature reproducibility hash checks via private import boundary only
"""
from __future__ import annotations

from backend.nexus_deep_license_inference.campaign import run_campaign, write_campaign_artifacts
from backend.nexus_deep_license_inference.constants import (
    BRANCH,
    COVERAGE_AREAS,
    LANE,
    PACKAGE,
    PROGRAM_ID,
    SCHEMA,
)
from backend.nexus_deep_license_inference.feature_repro_boundary import run_feature_repro_checks
from backend.nexus_deep_license_inference.inference_attacks import run_deep_inference_attacks
from backend.nexus_deep_license_inference.license_enforcement import run_license_enforcement_attacks
from backend.nexus_deep_license_inference.schema_fuzz import run_schema_fuzz_attacks

__all__ = [
    "BRANCH",
    "COVERAGE_AREAS",
    "LANE",
    "PACKAGE",
    "PROGRAM_ID",
    "SCHEMA",
    "run_campaign",
    "run_deep_inference_attacks",
    "run_feature_repro_checks",
    "run_license_enforcement_attacks",
    "run_schema_fuzz_attacks",
    "write_campaign_artifacts",
]
