"""V16-B Counterfactual Replay Engine — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v16_b_counterfactual_replay_engine"
SCHEMA_REPLAY = "v16_b_counterfactual_replay_result"
SCHEMA_PATH = "v16_b_counterfactual_path_outcome"
SCHEMA_COMPARABILITY = "v16_b_counterfactual_comparability"
SCHEMA_THREE_PASS = "v16_b_counterfactual_three_pass"
SCHEMA_FIXTURES = "v16_b_counterfactual_fixtures"
SCHEMA_DETERMINISTIC = "v16_b_counterfactual_deterministic_replay"

PACKAGE = "backend.nexus_counterfactual_replay_v16"
LANE = "V16-B"
LANE_NAME = "COUNTERFACTUAL_REPLAY_ENGINE"
BRANCH = "feature/v16-counterfactual-replay-engine"
ARTIFACT_REL = "artifacts/readiness/immutable/v16_counterfactual_replay"
BASE_COMMIT = "f01407e5d7c7e4c00e0eb1616dc5ef74d91a58b5"

# Alternate path inventory (required coverage).
ALTERNATE_PATHS: tuple[str, ...] = (
    "no_entry",
    "delay_entry",
    "early_entry",
    "reverse",
    "alt_stop",
    "alt_take_profit",
    "alt_size",
    "wait_confirm",
    "alt_strategy_expert",
    "exit_on_regime_transition",
    "block_low_data_trust",
)

STRATEGY_EXPERTS: tuple[str, ...] = (
    "TREND",
    "MEAN_REVERSION",
    "BREAKOUT",
    "LIQUIDATION",
    "FUNDING",
    "OPEN_INTEREST",
    "EVENT",
    "VOLATILITY",
    "CROSS_ASSET",
    "DEFENSIVE_NO_TRADE",
)

COMPARABILITY_GRADES: tuple[str, ...] = (
    "FULLY_COMPARABLE",
    "PARTIALLY_COMPARABLE",
    "NOT_COMPARABLE",
    "BLOCKED_INSUFFICIENT_COVERAGE",
)

COVERAGE_STATES: tuple[str, ...] = (
    "COMPLETE",
    "PARTIAL",
    "MISSING_PIT",
    "MISSING_COST",
    "MISSING_PATH_SERIES",
    "LOW_DATA_TRUST",
)

DISCLAIMER = (
    "COUNTERFACTUAL_PROFIT_IS_NOT_REAL_PERFORMANCE: "
    "alternate-path PnL is hypothetical, cost-adjusted, and must never be "
    "reported as live/demo ledger performance."
)

HARD_BANS: tuple[str, ...] = (
    "no_future_leakage",
    "no_rewrite_real_ledger",
    "no_counterfactual_profit_as_real_performance",
    "no_status_json_lane_artifact",
    "no_status_report_artifact",
    "no_demo_shadow_exchange_write",
    "no_mainnet_real_money",
    "no_oos_walkforward",
    "no_auto_integrate",
    "no_secret_logging",
    "no_silent_impute_missing_bars",
    "no_pit_bypass",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_counterfactual_replay_v16/",
    "tools/research/counterfactual_replay_v16/",
    "tests/counterfactual_replay_v16/",
    ARTIFACT_REL + "/",
)

PROHIBITED_PATHS_UNTOUCHED: tuple[str, ...] = (
    "frontend",
    "backend/nexus_demo_execution",
    "backend/api",
    "other_v16_lane_owned_paths",
)

FIXTURE_LABEL = "COUNTERFACTUAL_FIXTURE_NOT_REAL_LEDGER"
REPLAY_LABEL = "COUNTERFACTUAL_REPLAY_HYPOTHETICAL_ONLY"
DATA_TRUST_BLOCK_THRESHOLD = 0.45
DEFAULT_SEED = "v16b-counterfactual-default"
DEFAULT_DELAY_BARS = 2
DEFAULT_EARLY_BARS = 2
DEFAULT_ALT_SIZE_SCALE = 0.5
DEFAULT_ALT_STOP_MULT = 0.7
DEFAULT_ALT_TP_MULT = 1.3
DEFAULT_CONFIRM_BARS = 1

FORBIDDEN_LOG_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "token",
        "private_key",
        "authorization",
        "bybit_api_key",
        "bybit_api_secret",
        "account_balance",
        "wallet_address",
    }
)
