"""Founder-private Observability SLO V11.1 — constants, hard bans, schemas."""
from __future__ import annotations

SCHEMA_SLO_DEFINITIONS = "v11_1_private_observability_slo_definitions"
SCHEMA_ALERT = "v11_1_private_observability_alert"
SCHEMA_SNAPSHOT = "v11_1_private_observability_domain_health"
SCHEMA_STATUS = "v11_1_private_observability_slo_status"
SCHEMA_HARD_BANS = "v11_1_private_observability_hard_bans"
SCHEMA_SECRET_SCAN = "v11_1_private_observability_secret_scan"

PACKAGE = "backend.nexus_observability"
LANE = "S2"
LANE_NAME = "FOUNDER_PRIVATE_OBSERVABILITY_SLO"
BRANCH = "feature/v11_1-private-observability-slo"
ARTIFACT_REL = "artifacts/readiness/immutable/v11_1_observability"
BASE_COMMIT = "5b1d47543523f7e5be88da63256904171ce45165"

# Evidence / domain freshness (seconds)
STALENESS_THRESHOLD_SECONDS = 300.0

# Provider capacity heuristics
PROVIDER_CAPACITY_PENDING_RATIO = 0.25  # pending / (success+pending)
PROVIDER_MIN_SUCCESS_FOR_CAPACITY = 80
PROVIDER_CAPACITY_BLOCKING_STATUSES = frozenset(
    {
        "RATE_LIMITED",
        "CIRCUIT_OPEN",
        "BUCKET_THROTTLED",
        "TIMEOUT",
        "INCOMPLETE_PROVIDER_CAPACITY",
    }
)

# Storage floor (align with microstructure V10)
GIB = 1024**3
DEFAULT_MINIMUM_FREE_DISK_BYTES = 30 * GIB

# SLO score bands
SLO_HEALTHY_MIN = 85.0
SLO_DEGRADED_MIN = 65.0

# Domains covered by this package
OBSERVABILITY_DOMAINS: tuple[str, ...] = (
    "decision_lifecycle",
    "session_lifecycle",
    "risk_gates",
    "execution_simulator",
    "provider_health",
    "reflection_queue",
    "lesson_gate",
    "ledger_snapshot_checkpoint",
    "microstructure_health",
    "storage_budget",
    "kill_switch_readiness",
    "qualification_block_state",
)

# Alert classes required by Founder S2
ALERT_CLASSES: tuple[str, ...] = (
    "failure_state",
    "staleness",
    "data_quality",
    "ambiguous_state",
    "storage_floor",
    "provider_capacity",
)

# S2 + inherited hard bans (observability lane)
HARD_BANS: tuple[str, ...] = (
    "no_public_routes",
    "no_public_product_surface",
    "no_account_secrets",
    "no_api_keys_in_payloads",
    "no_wallet_or_balance_exposure",
    "no_strategy_parameters_in_payloads",
    "no_execution_mutation_endpoint",
    "no_exchange_writes",
    "no_demo_shadow_orders",
    "no_mainnet_real_money",
    "no_walk_forward_execution",
    "no_oos_execution",
    "no_strategy_selection_or_promotion",
    "no_event_study_start",
    "no_silent_ambiguous_continue",
    "read_only_only",
)

FORBIDDEN_OBSERVABILITY_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "token",
        "private_key",
        "authorization",
        "strategy_parameters",
        "account_balance",
        "wallet_address",
        "bybit_api_key",
        "bybit_api_secret",
    }
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_observability",
    "tools/research/run_private_observability_slo_v11_1.py",
    "tests/test_private_observability_slo_v11_1.py",
    ARTIFACT_REL,
)

PROHIBITED_PATHS_UNTOUCHED: tuple[str, ...] = (
    "frontend",
    "backend/nexus_demo_execution",
    "backend/api",  # no new public / founder mutation routes in this lane
    "other_v11_1_lane_owned_paths",
    "pr26_public_surfaces",
)
