"""V17 deep engineering — license enforcement + public inference constants."""
from __future__ import annotations

SCHEMA = "v17_deep_license_inference_v1"
SCHEMA_CAMPAIGN = "v17_deep_license_inference_campaign_v1"
SCHEMA_REDTEAM = "v17_deep_license_inference_redteam_v1"
LANE = "V17-DEEP-LICENSE-INFERENCE"
LANE_NAME = "LICENSE_ENFORCEMENT_AND_PUBLIC_INFERENCE"
BRANCH = "feature/v17-deep-license-inference-attacks"
PROGRAM_ID = "NEXUS_V17_DEEP_LICENSE_INFERENCE"
PUBLIC_BASE_SHA = "41c0fad533df4e63ed738b8c583f75564aa58c8e"
PRIVATE_TIP_SHA = "a43317e2f85afde75e850ffa4ef465c834fd7a6a"
ARTIFACT_REL = "artifacts/readiness/immutable/v17_deep_license_inference"
PACKAGE = "backend.nexus_deep_license_inference"

# Restricted license postures that must never leak to member UI as Live.
RESTRICTED_LICENSE_STATUSES: tuple[str, ...] = (
    "LICENSE_REVIEW_REQUIRED",
    "TRAINING_FORBIDDEN",
    "REDISTRIBUTION_FORBIDDEN",
)

# Candidate private worktrees for gold-factory hash checks (import boundary only).
PRIVATE_GOLD_FACTORY_CANDIDATES: tuple[str, ...] = (
    r"D:\NEXUS_RUNTIME\worktrees\v17_single_tip_integration",
    r"D:\NEXUS_RUNTIME\worktrees\v17_g_feature_factory",
    r"D:\NEXUS_RUNTIME\worktrees\v17_deep_ingest_contamination",
    r"D:\NEXUS_RUNTIME\worktrees\v17_deep_pit_survivorship",
)

HARD_BANS: tuple[str, ...] = (
    "no_restricted_license_as_live",
    "no_license_review_member_live",
    "no_training_forbidden_member_live",
    "no_redistribution_forbidden_member_live",
    "no_private_threshold_inference",
    "inference_attack_survivors_must_be_0",
    "no_allowlist_schema_smuggle",
    "no_private_gold_factory_exposure_in_public_tree",
    "no_real_money",
    "no_mainnet",
    "no_exchange_write",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "no_auto_integrate",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_deep_license_inference/",
    "tests/deep_license_inference/",
    "tools/research/deep_license_inference/",
    ARTIFACT_REL + "/",
    "backend/nexus_pub17_global_market_contracts/dto.py",
)

NON_CLAIMS: tuple[str, ...] = (
    "No PR26/PR27 merge",
    "No exchange/mainnet/real-money capability",
    "No private gold factory copied into public tree",
    "Private tip accessed via import boundary only when present",
    "No acceleration report edit",
)

EXPECTED_MIN_ATTACKS = 12
EXPECTED_MIN_TESTS = 10

COVERAGE_AREAS: tuple[str, ...] = (
    "license_enforcement_attacks",
    "public_inference_leakage_attacks",
    "schema_fuzzing_public_dto_allowlist",
    "feature_reproducibility_hash_import_boundary",
)
