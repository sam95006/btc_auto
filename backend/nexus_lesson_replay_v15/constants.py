"""V15-I Reflection and Lesson Replay Lab — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v15_i_reflection_lesson_replay_lab"
SCHEMA_REPLAY = "v15_i_lesson_replay_lab_report"
SCHEMA_GATE = "v15_i_real_lesson_prevention_gate"
SCHEMA_TWO_PASS = "v15_i_lesson_replay_two_pass"
SCHEMA_SECRET_SCAN = "v15_i_lesson_replay_secret_scan"
SCHEMA_CLASSIFICATION = "v15_i_process_classification"
SCHEMA_SIM_TRADES = "v15_i_historical_simulated_trades"
SCHEMA_FIXTURES = "v15_i_labeled_fixture_controls"

PACKAGE = "backend.nexus_lesson_replay_v15"
LANE = "V15-I"
LANE_NAME = "REFLECTION_AND_LESSON_REPLAY_LAB"
BRANCH = "feature/v15-reflection-lesson-replay"
ARTIFACT_REL = "artifacts/readiness/immutable/v15_reflection_lesson_replay"
BASE_COMMIT = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"
CANONICAL_CHECKPOINT_PATH = r"D:\NEXUS\btc_bot\.nexus_runtime\blind_reflection_v23_checkpoint.json"

# Incomplete V2.3 SoT (canonical checkpoint counters; never claim complete).
SOT_GROQ_SUCCESS = 53
SOT_GROQ_PENDING = 27
SOT_SAMBANOVA_SUCCESS = 16
SOT_SAMBANOVA_PENDING = 10
SOT_CASE_COUNT = 80
SOT_STAGE = "PROVIDER_CAPACITY_BLOCKED"
SOT_V2_3_COMPLETE = False
SOT_TERMINAL_STATUS = "INCOMPLETE_PROVIDER_CAPACITY"

PROCESS_CLASSES: tuple[str, ...] = (
    "GOOD_PROCESS_WIN",
    "GOOD_PROCESS_LOSS",
    "BAD_PROCESS_WIN",
    "BAD_PROCESS_LOSS",
    "UNDETERMINED",
)

INFORMATIVE_CLASSES = frozenset(
    {
        "GOOD_PROCESS_WIN",
        "GOOD_PROCESS_LOSS",
        "BAD_PROCESS_WIN",
        "BAD_PROCESS_LOSS",
    }
)

HARD_BANS: tuple[str, ...] = (
    "no_policy_effect_lessons_while_v23_incomplete",
    "no_fixture_as_real_policy_effect_proof",
    "no_loss_as_automatic_bad_process",
    "no_risk_leverage_size_stop_promotion_mutation",
    "no_profitability_claim",
    "no_fabricated_ai_learning",
    "no_demo_shadow_exchange_write",
    "no_mainnet_real_money",
    "no_oos_walkforward",
    "no_pr27_merge",
    "no_auto_integrate",
    "no_v23_complete_claim",
    "no_secret_logging",
    "no_status_json_lane_artifact",
    "no_real_lesson_prevention_until_v23_verified",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_lesson_replay_v15/",
    "tools/research/lesson_replay_v15/",
    "tests/lesson_replay_v15/",
    ARTIFACT_REL + "/",
)

PROHIBITED_PATHS_UNTOUCHED: tuple[str, ...] = (
    "frontend",
    "backend/nexus_demo_execution",
    "backend/api",
    "pr27_merge_surfaces",
    "other_v15_lane_owned_paths",
)

CONTROL_FIXTURE_LABEL = "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"
HISTORICAL_SIM_LABEL = "HISTORICAL_SIMULATED_TRADE_NOT_LIVE_EXCHANGE"
GENUINE_PROCESS_LABEL = "GENUINE_HISTORICAL_PROCESS_RECORD_SIMULATED"
REPLAY_LAB_LABEL = "LESSON_REPLAY_LAB_NOT_REAL_POLICY_EFFECT"
REAL_PROOF_LABEL = "REAL_POLICY_EFFECT_LESSON_PREVENTION"

FORBIDDEN_LOG_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "token",
        "private_key",
        "authorization",
        "raw_prompt",
        "raw_response",
        "bybit_api_key",
        "bybit_api_secret",
        "account_balance",
        "wallet_address",
        "strategy_parameters",
    }
)

RISK_STATIC_FIELDS: tuple[str, ...] = (
    "risk_limits_changed",
    "leverage_changed",
    "position_size_changed",
    "stops_changed",
    "strategy_parameters_changed",
    "promotion_state_changed",
    "profitability_claimed",
)

FORBIDDEN_EFFECTS = frozenset(
    {
        "increase_leverage",
        "increase_size",
        "weaken_cost_gate",
        "weaken_risk_gate",
        "widen_stop",
        "remove_deterministic_block",
        "permanent_strategy_parameter_change",
        "online_weight_training",
        "automatic_policy_promotion",
    }
)

ALLOWED_EFFECTS = frozenset(
    {
        "candidate_rejected",
        "additional_confirmation_required",
        "confidence_reduced",
        "temporary_symbol_block",
        "temporary_component_context_block",
        "stale_data_block",
        "cost_gate_block",
        "risk_gate_block",
        "ADDITIONAL_CONFIRMATION_REQUIRED",
        "CANDIDATE_REJECTED",
        "CONFIDENCE_REDUCED",
        "TEMPORARY_SYMBOL_BLOCK",
        "TEMPORARY_COMPONENT_CONTEXT_BLOCK",
        "STALE_DATA_BLOCK",
        "COST_GATE_BLOCK",
        "RISK_GATE_BLOCK",
        "NONE",
        "OBSERVE_ONLY",
    }
)
