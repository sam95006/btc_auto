"""Founder V15-G OOS Reservation and Seal Control constants."""
from __future__ import annotations

from pathlib import Path

SCHEMA_ID = "FOUNDER_V15_G_OOS_RESERVATION_SEAL_CONTROL"
LANE = "V15-G"
LANE_NAME = "OOS_RESERVATION_AND_SEAL_CONTROL"
BRANCH = "feature/v15-oos-reservation-control"
BASE_COMMIT = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"

ARTIFACT_REL = Path("artifacts/readiness/immutable/v15_oos_seal")

INFRA_STATUS_BLOCKED_READY = "BLOCKED_READY"
CONTROL_STATUS_READY = "SEAL_CONTROL_READY"
PLAN_STATUS_PLANNED_NOT_RESERVED = "PLANNED_NOT_RESERVED"
SEAL_STATUS_PLAN_SEALED_NOT_RESERVED = "PLAN_SEALED_NOT_RESERVED"
SEAL_STATUS_REGENERATION_REJECTED = "SEAL_REGENERATION_REJECTED"
SEAL_STATUS_WRITE_ONCE_VIOLATION = "SEAL_WRITE_ONCE_VIOLATION"

FOUNDER_AUTH_SCOPE = "founder_v15_g_oos_reservation_seal"

HARD_BANS: tuple[str, ...] = (
    "no_real_oos_reservation",
    "no_oos_download",
    "no_oos_execution",
    "no_oos_consumption",
    "no_formal_walk_forward",
    "no_strategy_selection",
    "no_strategy_promotion",
    "no_demo_orders",
    "no_shadow_orders",
    "no_exchange_writes",
    "no_pr27_merge",
    "no_mainnet",
    "no_real_money",
    "no_profitability_claims",
    "no_auto_integrate",
    "no_status_json_report",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_oos_seal_control",
    "tools/research/oos_seal_control",
    "tests/oos_seal_control",
    "artifacts/readiness/immutable/v15_oos_seal",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "btc_bot/frontend/",
    "backend/nexus_demo_execution/",
)

EVIDENCE_CLASS = "FIXTURE_AND_CONTROL_PLANE_ONLY"
BLOCK_REASON = "REAL_OOS_RESERVATION_BANNED_V15_G"

REQUIRED_FALSE_FLAGS: tuple[str, ...] = (
    "oos_reserved",
    "oos_downloaded",
    "oos_executed",
    "oos_consumed",
)

BINDING_KINDS: tuple[str, ...] = (
    "candidate",
    "code",
    "parameter",
    "dataset",
)

# Forbidden human-facing status report filenames under owned artifact dir.
FORBIDDEN_STATUS_JSON_SUFFIX = "_status.json"
FORBIDDEN_STATUS_BASENAMES: tuple[str, ...] = (
    "status.json",
    "v15_g_status.json",
    "oos_seal_status.json",
    "lane_status.json",
)
