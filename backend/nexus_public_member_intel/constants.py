"""UX-B Member Web Intelligence Experience — constants and hard bans.

Public-safe member presentation only. Compatible with UX-A Public Intelligence
DTO V2 field names even when UX-A is not yet merged. Never imports private_core.
"""
from __future__ import annotations

SCHEMA_VERSION = "public_member_intel_experience_v1"
PACKAGE = "backend.nexus_public_member_intel"
LANE = "UX-B"
LANE_NAME = "MEMBER_WEB_INTELLIGENCE_EXPERIENCE"
BRANCH = "feature/v16-member-web-intelligence-experience"
BASE_COMMIT = "cbad07e94e40e60c4b144fe63b22f40d26d8cf95"
PASS_COUNT = 3

# Member experience lifecycle / presentation states (must remain distinct).
LIFECYCLE_STATES: tuple[str, ...] = (
    "OBSERVING",
    "AI_ANALYZING",
    "AI_SUGGESTION",
    "RISK_REVIEW",
    "READY",
    "ENTERED",
    "MANAGING",
    "EXITED",
    "BLOCKED",
    "ABSTAINED",
    "SIMULATION",
    "HISTORICAL_REPLAY",
    "DEMO_DATA",
    "UNAVAILABLE",
    "STALE",
)

# Directional member postures (suggestion-only; never filled orders).
MEMBER_POSTURES: tuple[str, ...] = ("LONG", "SHORT", "WAIT", "ABSTAIN")

# Funnel stages (ordered).
FUNNEL_STAGES: tuple[tuple[str, str], ...] = (
    ("markets_scanned", "Markets scanned"),
    ("liquidity", "Liquidity"),
    ("data_quality", "Data quality"),
    ("ai_analysis", "AI analysis"),
    ("cost_blocked", "Cost blocked"),
    ("risk_blocked", "Risk blocked"),
)

FUNNEL_STAGE_IDS: tuple[str, ...] = tuple(s[0] for s in FUNNEL_STAGES)

# UX-A compatible recommendation states (nested intelligence block).
UXA_AI_RECOMMENDATION_STATES: frozenset[str] = frozenset(
    {"RECOMMEND", "HOLD", "WAIT", "ABSTAIN", "UNAVAILABLE"}
)

# UX-A compatible lifecycle statuses (nested intelligence block).
UXA_DECISION_LIFECYCLE_STATUSES: frozenset[str] = frozenset(
    {
        "OBSERVING",
        "EVIDENCE_REVIEW",
        "DECIDING",
        "MONITORING",
        "OUTCOME_REVIEW",
        "CLOSED",
        "ABSTAINED",
        "UNAVAILABLE",
    }
)

HARD_BANS: tuple[str, ...] = (
    "no_unavailable_as_zero",
    "no_fixture_as_live",
    "no_ai_suggestion_as_filled_order",
    "no_backtest_as_live",
    "no_fake_60_percent_guarantee",
    "no_private_core_imports",
    "no_exchange_write",
    "no_customer_trading",
    "no_demo_orders",
    "no_shadow_orders",
    "no_mainnet",
    "no_real_money",
    "no_status_json_artifact",
    "no_acceleration_report_edit",
    "no_execution_controls",
    "read_only_member_experience",
)

FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "private_key",
        "authorization",
        "strategy_parameters",
        "strategy_weights",
        "strategy_id",
        "account_balance",
        "wallet_address",
        "order_id",
        "client_order_id",
        "exchange_order_id",
        "founder_fill",
        "lesson_memory",
        "lesson_id",
        "execution_controls",
        "execution_route",
        "guarantee_pct",
        "win_rate_guarantee",
        "filled_order",
        "fill_price",
    }
)

PRIVATE_CORE_IMPORT_PREFIXES: tuple[str, ...] = (
    "backend.trading",
    "backend.fleets",
    "backend.wallet",
    "backend.nexus_demo_execution",
    "backend.nexus_autonomy",
    "backend.nexus_execution",
    "backend.nexus_research_validation",
    "backend.nexus_research",
    "backend.nexus_decision_memory_graph",
    "backend.nexus_strategy_expert_router",
    "backend.nexus_probabilistic_regime_v2",
    "backend.nexus_uncertainty_abstention",
    "backend.governance",
    "backend.portfolio",
    "backend.risk.risk_control_engine",
    "backend.risk.dynamic_leverage_engine",
    "ccxt",
    "pybit",
)

EXCHANGE_WRITE_MARKERS: tuple[str, ...] = (
    "api.bybit.com",
    "api-testnet.bybit.com",
    "api.binance.com",
    "testnet.binance.vision",
    "fapi.binance.com",
    "api.okx.com",
    "api.coinbase.com",
    "ccxt.",
    "EXCHANGE_WRITE",
    "place_order",
    "submit_order",
    "create_order",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_public_member_intel",
    "frontend/src/member/intel",
    "frontend/src/pages/member/MemberIntelligencePage.tsx",
    "tools/public/run_member_intel_three_passes.py",
    "tests/test_public_member_intel_experience.py",
)

# Banned claim strings that must never appear as live guarantees.
BANNED_GUARANTEE_CLAIMS: tuple[str, ...] = (
    "60% guarantee",
    "guaranteed 60%",
    "60% win rate guaranteed",
    "fake 60%",
)

DISPLAY_UNAVAILABLE = "UNAVAILABLE"
DISPLAY_DEMO_DATA = "DEMO_DATA"
DISPLAY_NO_DATA = "NO_DATA"
