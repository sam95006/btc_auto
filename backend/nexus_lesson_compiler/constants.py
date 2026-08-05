"""V16-E Lesson Compiler — constants and hard bans."""
from __future__ import annotations

PACKAGE = "NEXUS_LESSON_COMPILER"
SCHEMA = "v16_e_lesson_compiler"
LANE = "V16-E"
LANE_NAME = "LESSON_COMPILER"
CAMPAIGN_ID = "v16_e_lesson_compiler"
ARTIFACT_DIRNAME = "v16_lesson_compiler"
CATALOG_VERSION = "v16e.1.0"
RANDOM_SEED = 20260806
BASE_SHA = "f01407e5d7c7e4c00e0eb1616dc5ef74d91a58b5"
BRANCH = "feature/v16-lesson-compiler"

# Only legal promotion state this lane may emit.
LESSON_STATUS_CANDIDATE = "CANDIDATE"
FORBIDDEN_LESSON_STATUSES = frozenset(
    {
        "REPLAY_VALIDATED",
        "WALK_FORWARD_PENDING",
        "OOS_PENDING",
        "SHADOW_PENDING",
        "DEMO_PENDING",
        "ACTIVE",
        "DEGRADED",
        "RETIRED",
    }
)

HARD_BANS = frozenset(
    {
        "no_oos_consumption",
        "no_formal_walk_forward",
        "no_demo_orders",
        "no_shadow_orders",
        "no_exchange_write",
        "no_mainnet",
        "no_real_money",
        "no_profitability_claims",
        "no_edge_claims",
        "no_qualified_claims",
        "no_strategy_promotion",
        "no_lesson_promotion_to_active",
        "no_active_real_lessons",
        "no_production_risk_mutation",
        "no_production_leverage_mutation",
        "no_pr26_merge",
        "no_pr27_merge",
        "no_auto_integrate",
        "no_status_json",
        "no_private_core_deploy",
    }
)

OWNED_PATHS = (
    "backend/nexus_lesson_compiler",
    "tools/research/lesson_compiler",
    "tests/lesson_compiler",
    "artifacts/readiness/immutable/v16_lesson_compiler",
)

REQUIRED_LESSON_FIELDS = (
    "lesson_id",
    "status",
    "conditions",
    "then_action",
    "scope",
    "affected_expert",
    "regimes",
    "expiry",
    "evidence_count",
    "confidence",
    "contradictory_evidence",
    "author_model",
    "author_version",
    "mutates_production_risk",
    "mutates_production_leverage",
)

ALLOWED_CONDITION_OPS = frozenset({"EQ", "NE", "GT", "GE", "LT", "LE", "IN", "NOT_IN", "IS_FALSE", "IS_TRUE"})
ALLOWED_ACTION_KINDS = frozenset({"BLOCK", "ALLOW", "WAIT", "ABSTAIN", "REDUCE", "DEFER"})
ALLOWED_SCOPES = frozenset({"EXPERT", "SYMBOL", "REGIME", "STRATEGY_FAMILY", "GLOBAL_DEV"})
ALLOWED_REGIMES = frozenset(
    {
        "EXPANSION",
        "COMPRESSION",
        "TREND",
        "MEAN_REVERT",
        "LIQUIDATION_STRESS",
        "FUNDING_DISLOCATION",
        "ANY",
    }
)

# Process classes that must never seed "ALLOW" lessons (lucky bad process ≠ edge).
NON_LEARNING_PROCESS_CLASSES = frozenset(
    {
        "BAD_PROCESS_WIN",
        "INSUFFICIENT_EVIDENCE",
    }
)
# Only restrictive actions may be compiled from non-learning process classes.
ANTI_PATTERN_ACTION_KINDS = frozenset({"BLOCK", "ABSTAIN", "WAIT", "REDUCE", "DEFER"})

# Action kinds that would mutate production risk / leverage — hard reject.
BANNED_ACTION_TARGETS = frozenset(
    {
        "risk_limit",
        "risk_limits",
        "max_leverage",
        "leverage",
        "position_size",
        "position_notional",
        "stop_distance",
        "production_risk",
        "production_leverage",
    }
)

BANNED_CLAIM_FRAGMENTS = frozenset(
    {
        "QUALIFIED",
        "PROFITABLE",
        "OOS_PASS",
        "WALK_FORWARD_PASS",
        "DEMO_READY",
        "PROMOTION_READY",
        "EDGE_CONFIRMED",
        "ALPHA_PROVEN",
        "ACTIVE_LESSON",
    }
)

NON_CLAIMS = (
    "No predictive edge claim",
    "No profitability claim",
    "No qualification claim",
    "Lessons are CANDIDATE only; never ACTIVE",
    "Cannot mutate production risk or leverage",
    "Compile errors fail-closed",
    "No status JSON / runtime status report",
)

MIN_LESSON_COUNT = 8
EXPECTED_FIXTURE_COUNT = 8
