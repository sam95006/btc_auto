"""PUB2-A Public Decision Product E2E — constants and hard bans.

Customer-safe Decision Integrity journey. Never trades, never calls exchange
write APIs, never imports Founder Private Core, never fabricates customers.
"""
from __future__ import annotations

SCHEMA_VERSION = "public_decision_product_e2e_v1"
PACKAGE = "backend.nexus_public_decision_product"
LANE = "PUB2-A"
LANE_NAME = "PUBLIC_DECISION_PRODUCT_E2E"
BRANCH = "feature/public-v2-decision-product-e2e"
BASE_COMMIT = "5e93f677ece9f283aeade98657b5e3d5736991b5"

# Ordered customer-safe flow (no execution controls)
FLOW_STAGES: tuple[tuple[str, str], ...] = (
    ("market_observation", "Market Observation"),
    ("public_evidence", "Public Evidence"),
    ("counter_evidence", "Counter Evidence"),
    ("risk_conditions", "Risk Conditions"),
    ("public_decision_object", "Public Decision Object"),
    ("thesis_monitor", "Thesis Monitor"),
    ("outcome_review", "Outcome Review"),
    ("decision_memory", "Decision Memory"),
)

FLOW_STAGE_IDS: tuple[str, ...] = tuple(s[0] for s in FLOW_STAGES)
FLOW_STAGE_LABELS: tuple[str, ...] = tuple(s[1] for s in FLOW_STAGES)

# Explicitly excluded from the public product journey
EXCLUDED_STAGES: tuple[str, ...] = (
    "execution",
    "order_placement",
    "exchange_write",
    "demo_orders",
    "shadow_orders",
    "mainnet_trading",
    "copy_trading",
    "auto_trade",
)

HARD_BANS: tuple[str, ...] = (
    "no_customer_trading",
    "no_exchange_write",
    "no_demo_orders",
    "no_shadow_orders",
    "no_mainnet",
    "no_private_core_exposure",
    "no_execution_controls",
    "no_order_placement",
    "no_fabricated_customers",
    "no_fabricated_metrics",
    "no_human_facing_status_json",
    "no_pr26_pr27_merge",
    "read_only_journey_only",
    "staging_fixture_source_only",
)

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "private_key",
        "authorization",
        "strategy_parameters",
        "strategy_weights",
        "account_balance",
        "wallet_address",
        "bybit_api_key",
        "bybit_api_secret",
        "binance_api_key",
        "binance_api_secret",
        "lesson_memory_private",
        "founder_fill",
        "order_id",
        "client_order_id",
        "exchange_order_id",
        "paid_pilot_count",
        "real_participant_count",
        "fabricated_customer",
        "fabricated_metric",
        # Note: plural fabricated_customers/metrics are attestation bools, not banned keys
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
    "backend.governance",
    "backend.portfolio",
    "backend.risk.risk_control_engine",
    "backend.risk.dynamic_leverage_engine",
)

EXCHANGE_WRITE_MARKERS: tuple[str, ...] = (
    "api.bybit.com",
    "api-testnet.bybit.com",
    "api.binance.com",
    "testnet.binance.vision",
    "fapi.binance.com",
    "api.krx.com",
    "api.coinbase.com",
    "ccxt.",
    "EXCHANGE_WRITE",
    "place_order",
    "submit_order",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_public_decision_product",
    "tools/public/run_decision_product_e2e_passes.py",
    "tests/test_public_decision_product_e2e.py",
)

# Allowed dependency: read-only Public Decision Cloud (PUB-B) fixtures/surfaces
ALLOWED_PUBLIC_DEPENDENCIES: tuple[str, ...] = (
    "backend.nexus_public_decision_cloud",
)
