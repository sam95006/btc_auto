"""V18-F Shadow Decision Ledger — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v18_f_shadow_decision_ledger_v1"
RECORD_SCHEMA = "v18_f_shadow_decision_record_v1"
BRIDGE_SCHEMA = "v18_f_shadow_learning_bridge_v1"
SCHEMA_VERSION = 1
LANE = "V18-F"
LANE_NAME = "SHADOW_DECISION_LEDGER_AND_LEARNING_BRIDGE"
BRANCH = "feature/v18-shadow-decision-ledger"
BASE_COMMIT = "324e52f0573d7e3ad32feb2968274a52b8d8da75"
PACKAGE = "backend.nexus_shadow_decision_ledger"
ARTIFACT_REL = "artifacts/readiness/immutable/v18_shadow_decision_ledger"

# Shadow Decision lifecycle (NOT exchange Shadow Order lifecycle).
LIFECYCLE_STATES: tuple[str, ...] = (
    "OBSERVED",
    "CANDIDATE",
    "REVIEWED",
    "SHADOW_READY",
    "SHADOW_OPENED",
    "SHADOW_MANAGING",
    "SHADOW_CLOSED",
    "OUTCOME_PENDING",
    "OUTCOME_RECORDED",
    "REFLECTION_PENDING",
    "REFLECTED",
)

TERMINAL_STATES: frozenset[str] = frozenset({"REFLECTED"})

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "OBSERVED": frozenset({"CANDIDATE"}),
    "CANDIDATE": frozenset({"REVIEWED"}),
    "REVIEWED": frozenset({"SHADOW_READY"}),
    "SHADOW_READY": frozenset({"SHADOW_OPENED"}),
    # SHADOW_OPENED = internal virtual research position ONLY (never exchange order).
    "SHADOW_OPENED": frozenset({"SHADOW_MANAGING", "SHADOW_CLOSED"}),
    "SHADOW_MANAGING": frozenset({"SHADOW_CLOSED"}),
    "SHADOW_CLOSED": frozenset({"OUTCOME_PENDING"}),
    "OUTCOME_PENDING": frozenset({"OUTCOME_RECORDED"}),
    "OUTCOME_RECORDED": frozenset({"REFLECTION_PENDING"}),
    "REFLECTION_PENDING": frozenset({"REFLECTED"}),
    "REFLECTED": frozenset(),
}

# Public surface invariants — always enforced.
PUBLIC_FIELD_INVARIANTS: dict[str, object] = {
    "actual_ordered": False,
    "actual_filled": False,
    "exchange_order_id": None,
}

SHADOW_DECISION_KINDS: tuple[str, ...] = (
    "LONG",
    "SHORT",
    "WAIT",
    "ABSTAIN",
)

REQUIRED_PERSIST_FIELDS: tuple[str, ...] = (
    "shadow_decision_id",
    "lifecycle_state",
    "market_snapshot",
    "universe_decision",
    "candidate",
    "ai_suggestion",
    "critic",
    "deterministic_risk",
    "final_shadow_decision",
    "subsequent_outcome",
    "costs",
    "invalidation",
    "process_classification",
    "counterfactual_refs",
    "lesson_candidate_refs",
    "actual_ordered",
    "actual_filled",
    "exchange_order_id",
)

HARD_BANS: tuple[str, ...] = (
    "no_shadow_orders",
    "no_demo_orders",
    "no_exchange_write",
    "no_mainnet",
    "no_real_money",
    "no_actual_ordered",
    "no_actual_filled",
    "no_exchange_order_id",
    "no_active_lessons",
    "no_lesson_promotion_to_active",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "no_archive_rebuild",
    "no_rewrite_sealed_record",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_shadow_decision_ledger",
    "tests/shadow_decision_ledger",
    "artifacts/readiness/immutable/v18_shadow_decision_ledger",
)

NON_CLAIMS: tuple[str, ...] = (
    "Shadow Decision is not an exchange order",
    "SHADOW_OPENED is an internal virtual research position only",
    "actual_ordered/actual_filled remain false; exchange_order_id remains null",
    "Learning bridge emits Lesson CANDIDATE only; never ACTIVE",
    "No Demo / mainnet / real-money path",
)

LESSON_STATUS_CANDIDATE = "CANDIDATE"
FORBIDDEN_LESSON_STATUSES = frozenset({"ACTIVE", "DEMO_PENDING", "SHADOW_PENDING"})
