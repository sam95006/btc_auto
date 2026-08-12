"""V17-H Training Dataset Compiler — constants, splits, hard bans."""
from __future__ import annotations

PACKAGE = "NEXUS_TRAINING_DATASET_COMPILER"
SCHEMA = "v17_h_training_dataset_compiler"
LANE = "V17-H"
LANE_NAME = "TRAINING_DATASET_COMPILER"
CAMPAIGN_ID = "v17_h_training_dataset_compiler"
ARTIFACT_DIRNAME = "v17_training_dataset_compiler"
CATALOG_VERSION = "v17h.1.0"
RANDOM_SEED = 20260806
SPLIT_SEED = 2026080617
BASE_SHA = "66a0f7827d5709fc09bc8c7495e93a4089eb28de"
BRANCH = "feature/v17-training-dataset-compiler"

# Canonical dataset partitions — must remain mutually exclusive.
DATASET_SPLITS = (
    "DEVELOPMENT",
    "VALIDATION",
    "WALK_FORWARD_RESERVED",
    "OOS_RESERVED",
    "SHADOW",
    "DEMO",
    "REAL_PRIVATE",
)

# Only these splits may feed offline training / benchmark interfaces this round.
TRAINABLE_SPLITS = frozenset({"DEVELOPMENT", "VALIDATION"})

# Sealed / reserved — labeled and partitioned but never consumed for training.
RESERVED_SPLITS = frozenset(
    {
        "WALK_FORWARD_RESERVED",
        "OOS_RESERVED",
        "SHADOW",
        "DEMO",
        "REAL_PRIVATE",
    }
)

# Labels supported this round (targets as labels only — no live inference claims).
TARGET_LABELS = (
    "REGIME",
    "VOL_FORECAST",
    "LIQUIDITY_STRESS",
    "CANDIDATE_RANKING",
    "STRATEGY_ROUTING",
    "ABSTENTION",
    "ERROR_CLASSIFICATION",
    "COUNTERFACTUAL",
)

CONSUMER_ROLES = (
    "NUMERIC_STAT_MODEL",
    "LLM_REASONER",
)

HARD_BANS = frozenset(
    {
        "no_formal_walk_forward",
        "no_untouched_oos",
        "no_oos_consumption",
        "no_real_promotion",
        "no_real_lesson_activation",
        "no_mainnet",
        "no_real_money",
        "no_exchange_write",
        "no_demo_orders",
        "no_shadow_orders",
        "no_pr26_merge",
        "no_pr27_merge",
        "no_auto_integrate",
        "no_status_json",
        "no_private_core_deploy",
        "no_llm_sole_tick_consumer",
        "no_reserved_split_training",
        "no_lookahead_contamination",
        "no_cross_split_leak",
    }
)

OWNED_PATHS = (
    "backend/nexus_training_dataset_compiler",
    "tools/research/training_dataset_compiler",
    "tests/training_dataset_compiler",
    "artifacts/readiness/immutable/v17_training_dataset_compiler",
)

REQUIRED_SAMPLE_FIELDS = (
    "sample_id",
    "symbol",
    "ts_ms",
    "feature_cutoff_ms",
    "label_available_ms",
    "split",
    "target_label",
    "features",
    "label_payload",
    "provenance",
    "consumer_plan",
)

REQUIRED_FALSE_FLAGS = (
    "formal_walk_forward_executed",
    "untouched_oos_executed",
    "oos_consumed",
    "real_promotion_executed",
    "real_lesson_activated",
    "mainnet_touched",
    "real_money_touched",
    "exchange_write_attempted",
    "demo_order_placed",
    "shadow_order_placed",
    "pr26_merge_attempted",
    "pr27_merge_attempted",
    "auto_integrate_attempted",
    "status_json_written",
    "llm_sole_tick_consumer",
)

# Deterministic bucket weights for DEVELOPMENT vs VALIDATION when assigning
# trainable rows that do not declare an explicit split. Reserved splits are
# NEVER produced by hashing — only by explicit fixture declaration.
TRAINABLE_SPLIT_WEIGHTS = (
    ("DEVELOPMENT", 80),
    ("VALIDATION", 20),
)

MIN_FIXTURE_SAMPLES = 14
EXPECTED_FIXTURE_SAMPLES = 14
EXPECTED_CONTAMINATION_ATTACKS = 12

NON_CLAIMS = (
    "Labels only — no live predictive edge claim",
    "No formal walk-forward execution this round",
    "No untouched OOS execution this round",
    "No real Lesson activation",
    "No mainnet / real-money",
    "LLM is never the sole tick consumer",
    "Reserved splits are partitioned but not training-consumable",
)
