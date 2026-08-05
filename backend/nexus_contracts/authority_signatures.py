"""Authority signature patterns used by graph builders and CI gates."""
from __future__ import annotations

from typing import Any

# Private Core package roots scanned for authority competition.
PRIVATE_CORE_SCAN_ROOTS: tuple[str, ...] = (
    "backend/nexus_execution",
    "backend/nexus_autonomy",
    "backend/nexus_provider",
    "backend/nexus_private_control",
    "backend/nexus_recovery",
    "backend/nexus_runtime",
    "backend/nexus_reflection",
    "backend/nexus_edge_discovery",
    "backend/nexus_real_shadow",
    "backend/nexus_control_plane",
    "backend/nexus_demo_execution",
    "backend/nexus_strategy_engine",
    "backend/nexus_research",
    "backend/nexus_contracts",
)

# Additional paths that often host parallel authorities (audited, not owned).
EXTENDED_SCAN_ROOTS: tuple[str, ...] = (
    "backend/risk",
    "backend/trading",
    "backend/autonomy",
    "backend/governance",
    "backend/core",
    "backend/security",
    "tools/research",
)

# AST / text signatures that indicate an authority claim in a domain.
DOMAIN_SIGNATURES: dict[str, tuple[dict[str, Any], ...]] = {
    "execution": (
        {"kind": "class", "name_re": r"AutonomousExecutionSimulator"},
        {"kind": "assign", "name": "CANONICAL_EXECUTION_ENGINE"},
        {"kind": "assign", "name": "EXECUTION_MODE"},
        {"kind": "class", "name_re": r".*ExecutionEngine$"},
    ),
    "fill": (
        {"kind": "func", "name": "try_fill"},
        {"kind": "func", "name": "simulate_fill"},
        {"kind": "class", "name_re": r".*FillEngine.*"},
        {"kind": "assign", "name": "FILL_POLICY_DOC"},
    ),
    "cost": (
        {"kind": "assign", "name": "COST_MODEL_VERSION"},
        {"kind": "func", "name": "estimate_costs"},
        {"kind": "func", "name": "annotate_trade_costs"},
        {"kind": "func", "name_re": r".*cost_bridge.*"},
    ),
    "risk": (
        {"kind": "class", "name": "RiskLimits"},
        {"kind": "assign", "name": "FORBIDDEN_ACTIONS"},
        {"kind": "assign", "name": "MAX_LEVERAGE_CEILING"},
        {"kind": "class", "name_re": r"RiskControlEngine|RiskEngine"},
    ),
    "lifecycle": (
        {"kind": "assign", "name": "CANONICAL_STATES"},
        {"kind": "assign", "name": "VALID_TRANSITIONS"},
        {"kind": "class", "name_re": r".*StateMachine$"},
        {"kind": "class", "name_re": r".*LifecycleController$"},
    ),
    "checkpoint": (
        {"kind": "func", "name": "checkpoint_path"},
        {"kind": "func", "name": "recover_from_checkpoint"},
        {"kind": "class", "name": "CheckpointStore"},
        {"kind": "func", "name": "checkpoint_dest"},
        {"kind": "assign", "name": "CHECKPOINT_SCHEMA_V4"},
    ),
    "provider_retry": (
        {"kind": "func", "name": "parse_retry_after"},
        {"kind": "func", "name": "backoff_with_jitter"},
        {"kind": "func", "name": "exponential_backoff_with_jitter"},
        {"kind": "class", "name_re": r".*CircuitBreaker.*"},
        {"kind": "class", "name": "TokenBucket"},
    ),
}

# Env / legacy fallback markers (stale credential bridges).
STALE_ENV_FALLBACK_MARKERS: tuple[str, ...] = (
    "legacy_fallback",
    "legacy_env",
    "LEGACY_",
    "runtime_env_bridge",
    "GROQ_API_KEY",  # legacy single-key name vs PRIMARY/SECONDARY
    "BYBIT_M0_",
)

GRAPH_SCHEMA = "nexus_authority_graph_v1"
DRIFT_SCHEMA = "nexus_contract_drift_report_v1"
BASELINE_SCHEMA = "nexus_duplicate_authority_baseline_v1"
REMOVAL_SCHEMA = "nexus_removal_recommendations_v1"
