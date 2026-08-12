"""V18.1 Phase A — Live Shadow Runtime Conductor constants."""
from __future__ import annotations

from pathlib import Path

SCHEMA = "v18_1_live_shadow_runtime_conductor_v1"
SCHEMA_VERSION = 1
LANE = "V18_1_PHASE_A"
LANE_NAME = "Private Live Shadow Runtime Conductor"
PACKAGE = "backend.nexus_live_shadow_runtime"
BRANCH = "feature/nexus-private-core-v18-1-live-shadow-runtime"
PROGRAM_ID = "NEXUS_V18_1_PHASE_A_LIVE_SHADOW_RUNTIME"

# Formal runtime states ONLY (Founder directive §4.1).
RUNTIME_STATES: tuple[str, ...] = (
    "STARTING",
    "PREFLIGHT",
    "RUNNING",
    "DEGRADED",
    "PAUSED",
    "BACKOFF",
    "STOPPING",
    "STOPPED",
    "FAILED_SAFE",
)

TERMINAL_STATES: frozenset[str] = frozenset({"STOPPED", "FAILED_SAFE"})

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "STARTING": frozenset({"PREFLIGHT", "FAILED_SAFE", "STOPPING"}),
    "PREFLIGHT": frozenset({"RUNNING", "DEGRADED", "BACKOFF", "FAILED_SAFE", "STOPPING"}),
    "RUNNING": frozenset(
        {"DEGRADED", "PAUSED", "BACKOFF", "STOPPING", "FAILED_SAFE"}
    ),
    "DEGRADED": frozenset(
        {"RUNNING", "PAUSED", "BACKOFF", "STOPPING", "FAILED_SAFE"}
    ),
    "PAUSED": frozenset({"RUNNING", "DEGRADED", "BACKOFF", "STOPPING", "FAILED_SAFE"}),
    "BACKOFF": frozenset(
        {"RUNNING", "DEGRADED", "PAUSED", "STOPPING", "FAILED_SAFE"}
    ),
    "STOPPING": frozenset({"STOPPED", "FAILED_SAFE"}),
    "STOPPED": frozenset(),
    "FAILED_SAFE": frozenset(),
}

# Honest data_class values for this conductor (never claim continuous production ops).
DATA_CLASSES: frozenset[str] = frozenset(
    {
        "LIVE_READ_ONLY",
        "LIVE_PARTIAL_DEGRADED",
        "BOUNDED_LIVE_SMOKE",
        "FAILED_SAFE",
    }
)

DEFAULT_RUNTIME_ROOT = Path(r"D:\NEXUS_RUNTIME\live_shadow_runtime")
LOCK_NAME = "nexus_live_shadow_runtime_conductor"
HEARTBEAT_FILENAME = "heartbeat.json"
PID_FILENAME = "conductor.pid"
RESUME_FILENAME = "resume_state.json"
METRICS_FILENAME = "metrics.json"
PROJECTION_FILENAME = "public_safe_projection.jsonl"
LEDGER_FILENAME = "shadow_decision_ledger.jsonl"
EXIT_FILENAME = "smoke_exit.json"
STOP_REQUEST_FILENAME = "stop_requested"

# Public-safe projection allow-list (never secrets / order IDs / fills).
PROJECTION_ALLOW_FIELDS: frozenset[str] = frozenset(
    {
        "schema",
        "shadow_decision_id",
        "lifecycle_state",
        "final_shadow_decision",
        "data_class",
        "actual_ordered",
        "actual_filled",
        "exchange_order_id",
        "virtual_research_position",
        "sealed",
        "content_hash",
        "symbol",
        "decision",
        "decision_status",
        "as_of",
        "runtime_state",
        "cycle_index",
        "emitted_at",
    }
)

PROJECTION_DENY_FIELDS: frozenset[str] = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "private_key",
        "wallet",
        "account_balance",
        "order_id",
        "client_order_id",
        "fill_id",
        "leverage_override",
    }
)

HARD_BANS: tuple[str, ...] = (
    "no_exchange_write",
    "no_mainnet_trading_client",
    "no_demo_orders",
    "no_real_money",
    "no_actual_ordered",
    "no_actual_filled",
    "no_busy_loop",
    "no_duplicate_runtime_writer",
    "no_stale_decision_reuse_as_live",
    "no_force_long_short_on_insufficient_data",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_fabricated_live_success",
)

PRIORITY_SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_live_shadow_runtime/",
    "tests/live_shadow_runtime/",
)

# Resource budget defaults (bounded).
DEFAULT_MAX_CYCLES = 5
DEFAULT_MAX_SECONDS = 180
DEFAULT_CYCLE_SLEEP_SEC = 1.0
DEFAULT_BACKOFF_BASE_SEC = 2.0
DEFAULT_BACKOFF_MAX_SEC = 30.0
DEFAULT_MAX_DISK_BYTES = 256 * 1024 * 1024  # 256 MiB smoke budget
DEFAULT_HEARTBEAT_INTERVAL_SEC = 5.0

REUSED_V18_PACKAGES: tuple[str, ...] = (
    "backend.nexus_official_market_adapters",
    "backend.nexus_incremental_backfill_live_ingest",
    "backend.nexus_eligible_universe",
    "backend.nexus_live_opportunity_pipeline",
    "backend.nexus_ai_gateway_tool_sandbox",
    "backend.nexus_shadow_decision_ledger",
    "backend.nexus_data_trust_engine_v2",
    "backend.nexus_bronze_immutable_raw_lake",
    "backend.nexus_silver_symbol_identity",
    "backend.nexus_pit_revision_v17",
    "backend.nexus_gold_feature_factory",
    "backend.nexus_probabilistic_regime_v2",
    "backend.nexus_strategy_expert_router",
    "backend.nexus_uncertainty_abstention",
    "backend.runtime.single_instance_guard",
)
