"""PUB18-B — Decision Detail and Learning Transparency constants and hard bans.

Member may see decision timeline, regime, data trust, strategy expert label,
evidence / counter-evidence, risk reason, why WAIT/ABSTAIN, historical
similarity aggregate, shadow outcome, process classification aggregate, and
delayed learning summary.

Member must NEVER see private raw graph, exact proprietary thresholds, full
private strategy weights, Founder entry/exit, internal prompts, raw CoT, or
account data.
"""
from __future__ import annotations

SCHEMA = "pub18_b_decision_detail_transparency_v1"
SCHEMA_VERSION = "1"
PACKAGE = "backend.nexus_pub18_decision_detail"
LANE = "PUB18-B"
LANE_NAME = "DECISION_DETAIL_AND_LEARNING_TRANSPARENCY"
BRANCH = "feature/pub18-decision-detail-transparency"
BASE_COMMIT = "058c3e120e0709d7ff53e8338e431278fbbd093a"
PROGRAM_ID = "NEXUS_PUB18_DECISION_DETAIL_TRANSPARENCY"

# Exactly twelve member-visible transparency field ids (order matters for UI).
MEMBER_VISIBLE_FIELD_IDS: tuple[str, ...] = (
    "decision_timeline",
    "market_regime",
    "data_trust",
    "strategy_expert_label",
    "evidence",
    "counter_evidence",
    "risk_reason",
    "why_wait_abstain",
    "historical_similarity_aggregate",
    "shadow_outcome",
    "process_classification_aggregate",
    "delayed_learning_summary",
)

MEMBER_VISIBLE_FIELD_LABELS: dict[str, str] = {
    "decision_timeline": "Decision timeline",
    "market_regime": "Market Regime",
    "data_trust": "Data Trust",
    "strategy_expert_label": "Strategy Expert label",
    "evidence": "Evidence",
    "counter_evidence": "Counter Evidence",
    "risk_reason": "Risk reason",
    "why_wait_abstain": "Why WAIT / ABSTAIN",
    "historical_similarity_aggregate": "Historical similarity aggregate",
    "shadow_outcome": "Shadow outcome",
    "process_classification_aggregate": "Process classification aggregate",
    "delayed_learning_summary": "Delayed learning summary",
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
    "FIXTURE",
    "LIVE_READ_ONLY",
    "STALE",
)

FRESHNESS_STATES: tuple[str, ...] = (
    "FRESH",
    "STALE",
    "DEGRADED",
    "UNAVAILABLE",
    "PROVIDER_REQUIRED",
    "DEMO_DATA",
    "FIXTURE",
    "LIVE_READ_ONLY",
)

CHROME_LABELS: tuple[str, ...] = (
    "LIVE_READ_ONLY",
    "STALE",
    "UNAVAILABLE",
    "FIXTURE",
    "DEMO_DATA",
    "PROVIDER_REQUIRED",
)

HARD_BANS: tuple[str, ...] = (
    "no_private_raw_graph",
    "no_exact_proprietary_thresholds",
    "no_full_private_strategy_weights",
    "no_founder_entry_exit",
    "no_internal_prompts",
    "no_raw_cot",
    "no_account_data",
    "no_fake_live_zeros",
    "no_fabricated_live_values",
    "no_fixture_as_live",
    "no_member_exchange_write",
    "no_customer_trading",
    "no_mainnet",
    "no_real_money",
    "no_private_core_imports",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "read_only_member_decision_detail",
)

# Private fields that MUST NOT appear on the member decision detail surface.
FORBIDDEN_PRIVATE_FIELDS: frozenset[str] = frozenset(
    {
        "private_raw_graph",
        "raw_graph",
        "memory_graph",
        "decision_memory_graph",
        "graph_nodes",
        "graph_edges",
        "proprietary_threshold",
        "proprietary_thresholds",
        "exact_proprietary_threshold",
        "private_threshold",
        "private_thresholds",
        "entry_threshold",
        "exit_threshold",
        "threshold_table",
        "strategy_weights",
        "full_private_strategy_weights",
        "private_strategy_weights",
        "strategy_parameters",
        "strategy_params",
        "strategy_id",
        "founder_entry",
        "founder_exit",
        "exact_entry",
        "exact_exit",
        "exact_entry_exit",
        "entry_price",
        "exit_price",
        "stop_price",
        "stop_loss",
        "take_profit",
        "internal_prompt",
        "internal_prompts",
        "system_prompt",
        "prompt",
        "prompts",
        "raw_provider_prompt",
        "raw_provider_response",
        "raw_cot",
        "raw_chain_of_thought",
        "chain_of_thought",
        "cot",
        "account_data",
        "account_balance",
        "wallet_address",
        "api_key",
        "api_secret",
        "secret",
        "password",
        "private_key",
        "authorization",
        "order_id",
        "client_order_id",
        "exchange_order_id",
        "leverage",
        "position_size",
        "position_qty",
        "lesson_memory",
        "lesson_id",
        "private_lesson_memory",
    }
)

FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    set(FORBIDDEN_PRIVATE_FIELDS)
    | {
        "place_order",
        "submit_order",
        "create_order",
        "execute_trade",
        "execution_controls",
        "execution_route",
        "risk_governor_state",
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
    "backend.nexus_decision_memory_graph",
    "backend.nexus_strategy_expert_router",
    "backend.nexus_probabilistic_regime_v2",
    "backend.nexus_uncertainty_abstention",
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
    "backend/nexus_pub18_decision_detail",
    "frontend/src/member/decision_detail",
    "frontend/src/pages/member/MemberDecisionDetailPage.tsx",
    "tools/public/run_pub18_decision_detail_gate.py",
    "tests/pub18_decision_detail",
)

DISPLAY_UNAVAILABLE = "UNAVAILABLE"
DISPLAY_PROVIDER_REQUIRED = "PROVIDER_REQUIRED"
DISPLAY_DEMO_DATA = "DEMO_DATA"
DISPLAY_FIXTURE = "FIXTURE"
DISPLAY_STALE = "STALE"
DISPLAY_LIVE_READ_ONLY = "LIVE_READ_ONLY"

PASS_RECOMMENDATION = "NEXUS_PUB18_DECISION_DETAIL_TRANSPARENCY_PASS"
FAIL_RECOMMENDATION = "NEXUS_PUB18_DECISION_DETAIL_TRANSPARENCY_FAIL"
