"""PUB18-A — Live Funnel and Market Pulse constants and hard bans.

Member first screen + read-only universe funnel. Never imports private core.
Private tip 12f8cd8… is a contract reference only (projection shapes).
"""
from __future__ import annotations

SCHEMA = "pub18_a_live_funnel_market_pulse_v1"
SCHEMA_VERSION = "1"
PACKAGE = "backend.nexus_pub18_live_funnel"
LANE = "PUB18-A"
LANE_NAME = "LIVE_FUNNEL_AND_MARKET_PULSE"
BRANCH = "feature/pub18-live-funnel-market-pulse"
BASE_COMMIT = "058c3e120e0709d7ff53e8338e431278fbbd093a"
PRIVATE_CONTRACT_TIP = "12f8cd8aa30fb1242064c9f7644d537e15080c6c"
PROGRAM_ID = "NEXUS_PUB18_LIVE_FUNNEL_MARKET_PULSE"

# Member first-screen answer ids (order matters for UI).
FIRST_SCREEN_ANSWER_IDS: tuple[str, ...] = (
    "global_market_state",
    "crypto_derivatives_risk",
    "top_3_opportunities",
    "ai_posture",
    "supporting_evidence",
    "counter_evidence",
    "invalidation",
    "data_freshness",
    "data_class_label",
)

FIRST_SCREEN_QUESTIONS: dict[str, str] = {
    "global_market_state": "Global Market State",
    "crypto_derivatives_risk": "Crypto Derivatives Risk",
    "top_3_opportunities": "Top 3 Opportunities",
    "ai_posture": "AI posture",
    "supporting_evidence": "Supporting Evidence",
    "counter_evidence": "Counter Evidence",
    "invalidation": "Invalidation",
    "data_freshness": "Data Freshness",
    "data_class_label": "Shadow / Live / Fixture label",
}

# Public AI postures only (suggestion / research — never filled orders).
AI_POSTURES: tuple[str, ...] = ("LONG", "SHORT", "WAIT", "ABSTAIN")

# Honest data-class vocabulary — never fabricate LIVE zeros.
DATA_CLASS_LABELS: tuple[str, ...] = (
    "LIVE_READ_ONLY",
    "STALE",
    "UNAVAILABLE",
    "FIXTURE",
)

# Read-only funnel stages (Founder order).
FUNNEL_STAGES: tuple[tuple[str, str], ...] = (
    ("scanned", "Scanned"),
    ("data_available", "Data available"),
    ("liquidity", "Liquidity"),
    ("data_trust", "Data Trust"),
    ("candidate", "Candidate"),
    ("ai_review", "AI Review"),
    ("cost_blocked", "Cost Blocked"),
    ("risk_blocked", "Risk Blocked"),
    ("shadow_decisions", "Shadow Decisions"),
)

FUNNEL_STAGE_IDS: tuple[str, ...] = tuple(s[0] for s in FUNNEL_STAGES)

HARD_BANS: tuple[str, ...] = (
    "no_founder_positions",
    "no_exact_leverage",
    "no_private_thresholds",
    "no_real_order_ids",
    "no_private_lessons",
    "no_trade_buttons",
    "no_fake_live_zeros",
    "no_fixture_as_live",
    "no_unavailable_as_zero",
    "no_member_exchange_write",
    "no_customer_trading",
    "no_execution_controls",
    "member_execution_control_count_must_be_0",
    "no_private_core_imports",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "no_archive_rebuild",
    "read_only_member_first_screen",
)

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
        "strategy_parameters",
        "strategy_params",
        "strategy_weights",
        "strategy_id",
        "founder_position",
        "founder_positions",
        "lesson_memory",
        "lesson_id",
        "private_lesson",
        "private_lessons",
        "lesson_text",
    }
)

EXECUTION_CONTROL_KEYS: frozenset[str] = frozenset(
    {
        "execution_controls",
        "execution_control",
        "execution_route",
        "execution_routes",
        "place_order",
        "submit_order",
        "create_order",
        "execute_trade",
        "copy_trade",
        "auto_trade",
        "trade_now",
        "trade_button",
        "member_execution_controls",
    }
)

FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    set(FORBIDDEN_FOUNDER_FIELDS)
    | set(EXECUTION_CONTROL_KEYS)
    | {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "private_key",
        "authorization",
        "account_balance",
        "wallet_address",
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
    "backend.nexus_eligible_universe",
    "backend.nexus_live_opportunity_pipeline",
    "backend.nexus_shadow_decision_ledger",
    "backend.nexus_official_market_adapters",
    "backend.nexus_real_shadow",
    "backend.nexus_global_shadow",
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
    "trade_now",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_pub18_live_funnel",
    "frontend/src/member/live_funnel",
    "frontend/src/pages/member/MemberHomePage.tsx",
    "tools/public/run_pub18_live_funnel_gate.py",
    "tests/pub18_live_funnel",
)

DISPLAY_UNAVAILABLE = "UNAVAILABLE"
DISPLAY_STALE = "STALE"
DISPLAY_FIXTURE = "FIXTURE"
DISPLAY_LIVE_READ_ONLY = "LIVE_READ_ONLY"

PASS_RECOMMENDATION = "NEXUS_PUB18_LIVE_FUNNEL_MARKET_PULSE_PASS"
FAIL_RECOMMENDATION = "NEXUS_PUB18_LIVE_FUNNEL_MARKET_PULSE_FAIL"
