"""PUB18-C Founder Live Operations — panel + control catalogs."""
from __future__ import annotations

SCHEMA_ID = "NEXUS_FOUNDER_LIVE_OPERATIONS_PUB18_C"
LANE = "PUB18-C"
LANE_NAME = "FOUNDER_LIVE_OPERATIONS"

LIVE_OPS_PANEL_IDS: tuple[str, ...] = (
    "adapter_health",
    "ingest_rate_lag",
    "partition_health",
    "universe_funnel",
    "data_trust_distribution",
    "regime_distribution",
    "strategy_distribution",
    "uncertainty_distribution",
    "shadow_decision_states",
    "repeated_error_signatures",
    "ai_provider_health",
    "fallback_rate",
    "token_budget_telemetry",
    "disk_quota",
    "pipeline_pause_resume",
    "emergency_read_only_stop",
)

PANEL_TITLES: dict[str, str] = {
    "adapter_health": "Adapter Health",
    "ingest_rate_lag": "Ingest Rate / Lag",
    "partition_health": "Partition Health",
    "universe_funnel": "Universe Funnel",
    "data_trust_distribution": "Data Trust Distribution",
    "regime_distribution": "Regime Distribution",
    "strategy_distribution": "Strategy Distribution",
    "uncertainty_distribution": "Uncertainty Distribution",
    "shadow_decision_states": "Shadow Decision States",
    "repeated_error_signatures": "Repeated Error Signatures",
    "ai_provider_health": "AI Provider Health",
    "fallback_rate": "Fallback Rate",
    "token_budget_telemetry": "Token / Budget Telemetry",
    "disk_quota": "Disk Quota",
    "pipeline_pause_resume": "Pipeline Pause / Resume",
    "emergency_read_only_stop": "Emergency Read-Only Stop",
}

# Allowed Founder controls ONLY.
ALLOWED_CONTROLS: tuple[str, ...] = (
    "pause_ingest",
    "resume_ingest",
    "disable_provider",
    "disable_source",
    "force_read_only_degraded_mode",
    "export_evidence",
)

# Explicitly banned UI/actions — must never appear as executable controls.
BANNED_CONTROLS: tuple[str, ...] = (
    "trade_now",
    "override_risk",
    "force_long",
    "force_short",
    "change_leverage",
    "enable_mainnet",
)

# Alternate spellings / UI labels that must also never be actionable.
BANNED_CONTROL_ALIASES: tuple[str, ...] = (
    "trade now",
    "override Risk",
    "force LONG",
    "force SHORT",
    "change leverage",
    "enable mainnet",
    "force_LONG",
    "force_SHORT",
)

HARD_BANS: tuple[str, ...] = (
    "no_trade_now",
    "no_override_risk",
    "no_force_long_short",
    "no_change_leverage",
    "no_enable_mainnet",
    "no_exchange_write",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_report_archive_rebuild",
    "no_member_session_access",
    "no_fabricated_live_values",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_pub18_founder_live_ops",
    "backend/api/founder_private_routes.py",
    "frontend/src/founder/FounderLiveOpsPage.tsx",
    "frontend/src/founder/api.ts",
    "frontend/src/founder/types.ts",
    "frontend/src/founder/FounderOperatorShell.tsx",
    "frontend/src/App.tsx",
    "tests/pub18_founder_live_ops",
    "tools/public/run_pub18_founder_live_ops_gate.py",
)
