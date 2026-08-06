"""PUB17-B — Market Pulse and Top Opportunities constants and hard bans.

Member first-screen answers only. Never expose Founder private execution fields.
"""
from __future__ import annotations

SCHEMA = "pub17_b_market_pulse_opportunities_v1"
SCHEMA_VERSION = "1"
PACKAGE = "backend.nexus_pub17_market_pulse"
LANE = "PUB17-B"
LANE_NAME = "MARKET_PULSE_AND_TOP_OPPORTUNITIES"
BRANCH = "feature/pub17-market-pulse-opportunities"
BASE_COMMIT = "8391c17e2d0d0ea9ee69c8e253cc5d71f1456da3"
PROGRAM_ID = "NEXUS_PUB17_MARKET_PULSE_OPPORTUNITIES"

# Exactly nine member-first-screen answer ids (order matters for UI).
FIRST_SCREEN_ANSWER_IDS: tuple[str, ...] = (
    "global_market_state",
    "crypto_derivatives_risk",
    "top_3_markets_contracts",
    "ai_posture",
    "supporting_evidence",
    "counter_evidence",
    "invalidation",
    "data_freshness",
    "analysis_vs_actual_trading",
)

FIRST_SCREEN_QUESTIONS: dict[str, str] = {
    "global_market_state": "Global market state",
    "crypto_derivatives_risk": "Crypto derivatives risk",
    "top_3_markets_contracts": "Top 3 markets / contracts",
    "ai_posture": "AI posture",
    "supporting_evidence": "Supporting evidence",
    "counter_evidence": "Counter-evidence",
    "invalidation": "Invalidation",
    "data_freshness": "Data freshness",
    "analysis_vs_actual_trading": "Analysis vs actual trading",
}

# Public AI postures only (suggestion / research — never filled orders).
AI_POSTURES: tuple[str, ...] = ("LONG", "SHORT", "WAIT", "ABSTAIN")

# Honest availability / freshness vocabulary — never fabricate LIVE zeros.
AVAILABILITY_STATES: tuple[str, ...] = (
    "AVAILABLE",
    "PROVIDER_REQUIRED",
    "UNAVAILABLE",
    "BLOCKED",
    "DEMO_DATA",
)

FRESHNESS_STATES: tuple[str, ...] = (
    "FRESH",
    "STALE",
    "DEGRADED",
    "UNAVAILABLE",
    "PROVIDER_REQUIRED",
    "DEMO_DATA",
)

ANALYSIS_VS_TRADING_FLAGS: tuple[str, ...] = (
    "ANALYSIS_ONLY",
    "NOT_ACTUAL_TRADING",
    "PROVIDER_REQUIRED",
    "UNAVAILABLE",
)

HARD_BANS: tuple[str, ...] = (
    "no_position_size",
    "no_leverage",
    "no_exact_entry_stop",
    "no_order_id",
    "no_private_thresholds",
    "no_private_strategy_source",
    "no_fake_live_zeros",
    "no_fabricated_live_values",
    "no_member_exchange_write",
    "no_customer_trading",
    "no_mainnet",
    "no_real_money",
    "no_private_core_imports",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "read_only_member_first_screen",
)

# Founder private fields that MUST NOT appear on the member first screen.
FORBIDDEN_FOUNDER_FIELDS: frozenset[str] = frozenset(
    {
        "position_size",
        "position_qty",
        "qty",
        "size",
        "leverage",
        "exact_entry",
        "exact_stop",
        "entry_price",
        "stop_price",
        "stop_loss",
        "take_profit",
        "order_id",
        "order_ids",
        "client_order_id",
        "exchange_order_id",
        "private_threshold",
        "private_thresholds",
        "entry_threshold",
        "exit_threshold",
        "proprietary_threshold",
        "proprietary_thresholds",
        "threshold_table",
        "private_strategy_source",
        "strategy_source",
        "internal_strategy_source",
        "strategy_parameters",
        "strategy_params",
        "strategy_weights",
        "strategy_id",
    }
)

FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    set(FORBIDDEN_FOUNDER_FIELDS)
    | {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "private_key",
        "authorization",
        "account_balance",
        "wallet_address",
        "place_order",
        "submit_order",
        "create_order",
        "execute_trade",
        "execution_controls",
        "lesson_memory",
        "lesson_id",
    }
)

PRIVATE_CORE_IMPORT_PREFIXES: tuple[str, ...] = (
    "backend.trading",
    "backend.wallet",
    "backend.portfolio",
    "backend.fleets",
    "backend.nexus_demo_execution",
    "backend.nexus_autonomy",
    "backend.nexus_execution",
    "backend.nexus_strategy_engine",
    "backend.nexus_research",
    "backend.risk.dynamic_leverage_engine",
    "backend.risk.risk_control_engine",
    "ccxt",
    "pybit",
)

EXCHANGE_WRITE_MARKERS: tuple[str, ...] = (
    "EXCHANGE_WRITE=True",
    "MAINNET=True",
    "REAL_MONEY=True",
    "place_order",
    "submit_order",
    "create_order",
    "execute_trade",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_pub17_market_pulse",
    "frontend/src/member/pulse",
    "frontend/src/pages/member/MemberHomePage.tsx",
    "tools/public/run_pub17_market_pulse_gate.py",
    "tests/pub17_market_pulse",
)

DISPLAY_UNAVAILABLE = "UNAVAILABLE"
DISPLAY_PROVIDER_REQUIRED = "PROVIDER_REQUIRED"
DISPLAY_ANALYSIS_ONLY = "ANALYSIS_ONLY · NOT ACTUAL TRADING"

PASS_RECOMMENDATION = "NEXUS_PUB17_MARKET_PULSE_OPPORTUNITIES_PASS"
FAIL_RECOMMENDATION = "NEXUS_PUB17_MARKET_PULSE_OPPORTUNITIES_FAIL"
