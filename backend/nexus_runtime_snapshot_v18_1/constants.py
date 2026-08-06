"""V18.1 Phase B — shared public-safe Runtime Snapshot contract constants."""
from __future__ import annotations

from pathlib import Path

SCHEMA = "v18_1_runtime_snapshot_public_v1"
SCHEMA_VERSION = 1
LANE = "V18_1_PHASE_B"
LANE_NAME = "Public + Mobile Live Binding"
PACKAGE = "backend.nexus_runtime_snapshot_v18_1"
PROGRAM_ID = "NEXUS_V18_1_PHASE_B_RUNTIME_SNAPSHOT"
PUBLIC_BRANCH = "feature/nexus-public-v18-1-live-binding"
MOBILE_BRANCH = "feature/nexus-mobile-v18-1-live-binding"
PRIVATE_PHASE_A_TIP = "d64d1ec8fe76969a25fe682a0529b127be1a232a"
PUBLIC_BASE = "d4cfbf1c5611fdc6987ac902b697721b9162bd91"
MOBILE_BASE = "e173d8ed5a2ec28b3e6d77a20d220b98236d228b"

DEFAULT_RUNTIME_ROOT = Path(r"D:\NEXUS_RUNTIME\live_shadow_runtime")
HEARTBEAT_FILENAME = "heartbeat.json"
METRICS_FILENAME = "metrics.json"
PROJECTION_FILENAME = "public_safe_projection.jsonl"
EXIT_FILENAME = "smoke_exit.json"

# Member-facing runtime states (Founder §5.2). Internal conductor states map into these.
PUBLIC_RUNTIME_STATES: tuple[str, ...] = (
    "RUNNING",
    "DEGRADED",
    "PAUSED",
    "STOPPED",
    "UNAVAILABLE",
)

# Honest freshness / chrome labels when not live.
FRESHNESS_LABELS: tuple[str, ...] = (
    "FRESH",
    "STALE",
    "RUNTIME_STOPPED",
    "UNAVAILABLE",
    "LIVE_PARTIAL_DEGRADED",
    "LIVE_READ_ONLY",
)

# Required snapshot fields (Founder §5.1).
REQUIRED_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "runtime_state",
    "runtime_started_at",
    "runtime_last_cycle_at",
    "data_freshness",
    "source_health",
    "universe_funnel",
    "decision_counts",
    "top_opportunities",
    "shadow_status",
    "AI_gateway_status",
    "degraded_reasons",
    "actual_ordered",
    "actual_filled",
    "data_class",
    "as_of",
    "lineage_id",
)

# Allow-list of keys that may appear on the public snapshot (private→public projection).
SNAPSHOT_ALLOW_FIELDS: frozenset[str] = frozenset(
    {
        *REQUIRED_SNAPSHOT_FIELDS,
        "schema",
        "schema_version",
        "lane",
        "package",
        "display_label",
        "chrome_label",
        "binding_mode",
        "is_live_view",
        "last_updated",
        "heartbeat_at",
        "source_path",
        "projection_count",
        "read_only",
        "trade_buttons",
        "alerts",
        "hard_bans",
        "private_field_leak_count",
        "member_execution_control_count",
        "fixture_as_live_count",
        "ok",
        "error",
        "note",
    }
)

# Hard ban — never project these (Founder private / execution / secrets).
PRIVATE_BAN_FIELDS: frozenset[str] = frozenset(
    {
        "founder_capital",
        "account_balance",
        "wallet",
        "wallet_address",
        "api_key",
        "api_secret",
        "secret",
        "private_key",
        "order_id",
        "client_order_id",
        "exchange_order_id",
        "fill_id",
        "exact_entry",
        "exact_stop",
        "entry_price",
        "stop_loss",
        "leverage",
        "position_size",
        "strategy_weights",
        "private_threshold",
        "private_thresholds",
        "lesson_memory",
        "private_lesson",
        "raw_decision_memory",
        "internal_prompt",
        "chain_of_thought",
        "private_trade_ledger",
    }
)

# Alert truth kinds (Founder §5.4) — real runtime events only.
LIVE_ALERT_KINDS: tuple[str, ...] = (
    "REGIME_CHANGED",
    "DATA_TRUST_DEGRADED",
    "CANDIDATE_CREATED",
    "POSTURE_CHANGED",
    "SHADOW_OPENED",
    "SHADOW_CLOSED",
    "INVALIDATION_TRIGGERED",
    "PROVIDER_DEGRADED",
    "RUNTIME_STOPPED",
)

BANNED_ALERT_PHRASES: tuple[str, ...] = (
    "BUY NOW",
    "SELL NOW",
    "GUARANTEED",
    "PROFIT GUARANTEED",
    "SYSTEM BOUGHT FOR YOU",
    "COPY TRADE",
)

# Heartbeat older than this while claiming RUNNING/DEGRADED → STALE.
STALE_AFTER_SECONDS = 120

HARD_BANS: tuple[str, ...] = (
    "no_private_core_import",
    "no_private_field_leak",
    "no_fixture_as_live",
    "no_stale_as_live",
    "no_stopped_as_live",
    "no_member_execution_control",
    "no_exchange_write",
    "no_mainnet",
    "no_demo_orders",
    "no_real_money",
    "no_actual_ordered",
    "no_actual_filled",
    "no_hype_alerts",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "no_archive_rebuild",
    "no_apk_rebuild_unless_native_changed",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_runtime_snapshot_v18_1/",
    "tests/runtime_snapshot_v18_1/",
    "frontend/src/member/runtime_snapshot/",
)

# Never import private Phase A conductor package from public/mobile tips.
PRIVATE_CORE_IMPORT_PREFIXES: tuple[str, ...] = (
    "backend.nexus_live_shadow_runtime",
    "backend.trading",
    "backend.wallet",
    "backend.portfolio",
    "backend.nexus_execution",
    "backend.nexus_demo_execution",
    "backend.nexus_learning",
    "ccxt",
    "pybit",
)
