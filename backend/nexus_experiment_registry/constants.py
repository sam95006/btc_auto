"""V14-J Experiment Registry — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V14_J_EXPERIMENT_REGISTRY"
SCHEMA_VERSION = 1
RECORD_SCHEMA = "nexus_experiment_record_v14_j"
REGISTRY_SCHEMA = "nexus_experiment_registry_v14_j"
LANE = "V14-J"
LANE_NAME = "EXPERIMENT_REGISTRY_AND_REPRODUCIBILITY"
BRANCH = "feature/v14-experiment-registry"
BASE_COMMIT = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"

FEATURE_VERSION_DEFAULT = "v14_j_feature_surface_1"
EXECUTION_VERSION_DEFAULT = "autonomous_execution_simulator_v1_1"

# Identity fields that define "same experiment setup" for duplicate detection.
# Result hashes are intentionally excluded — divergent results under the same
# identity is a fail-closed conflict (non-determinism / cherry-pick attempt).
IDENTITY_FIELDS: tuple[str, ...] = (
    "mechanism_semantic_id",
    "data_lineage",
    "universe_checksum",
    "feature_version",
    "code_checksum",
    "parameter_checksum",
    "cost_version",
    "risk_version",
    "execution_version",
    "time_intervals",
    "development_only",
    "seeds",
)

REQUIRED_RECORD_KEYS: tuple[str, ...] = (
    "schema",
    "schema_version",
    "experiment_id",
    "mechanism_semantic_id",
    "data_lineage",
    "universe_checksum",
    "feature_version",
    "code_checksum",
    "parameter_checksum",
    "cost_version",
    "risk_version",
    "execution_version",
    "time_intervals",
    "development_only",
    "oos_consumed",
    "seeds",
    "result_hashes",
    "parent_experiment",
    "identity_fingerprint",
    "record_hash",
    "simulated_only",
    "exchange_write",
    "demo_order",
    "shadow_order",
    "learning_claim",
    "profitability_claim",
    "formal_walk_forward_executed",
    "oos_executed",
    "mainnet",
    "real_money",
)

HARD_BANS = {
    "pr27_merge": False,
    "deployment": False,
    "formal_walk_forward": False,
    "real_oos_execution": False,
    "real_oos_consumption": False,
    "demo_orders": False,
    "shadow_orders": False,
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "strategy_promotion": False,
    "profit_guarantee": False,
    "fabricated_strategy_edge": False,
    "fabricated_ai_learning": False,
    "auto_integration": False,
    "silent_cherry_picking": False,
}

HARD_BAN_FLAGS = {
    "simulated_only": True,
    "exchange_write": False,
    "demo_order": False,
    "shadow_order": False,
    "learning_claim": False,
    "profitability_claim": False,
    "formal_walk_forward_executed": False,
    "oos_executed": False,
    "mainnet": False,
    "real_money": False,
    "auto_integration": False,
}

OWNED_PATHS = [
    "backend/nexus_experiment_registry/",
    "tools/research/experiment_registry/",
    "tests/experiment_registry/",
    "artifacts/readiness/immutable/v14_experiment_registry/",
]

INTERVAL_CATEGORIES = frozenset({"development", "validation", "holdout_reserved", "oos"})
