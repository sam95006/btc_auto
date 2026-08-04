"""NEXUS Private Core Security Boundary V1 — constants and classifications."""
from __future__ import annotations

SCHEMA = "private_core_security_boundary_v1"
BOUNDARY_ID = "NEXUS_PRIVATE_CORE_SECURITY_BOUNDARY_V1"

# Exchange write / mutation method names (Bybit-style + local client methods).
EXCHANGE_WRITE_METHODS: frozenset[str] = frozenset(
    {
        "create_order",
        "create_market_order",
        "amend_order",
        "cancel_order",
        "cancel_all",
        "cancel_all_orders",
        "set_leverage",
        "switch_margin_mode",
        "set_trading_stop",
        "close_reduce_only",
        "withdraw",
        "transfer",
        "internal_transfer",
        "subaccount_transfer",
        "place_order",
        "submit_order",
    }
)

WRITE_PATH_FRAGMENTS: tuple[str, ...] = (
    "/v5/order/create",
    "/v5/order/amend",
    "/v5/order/cancel",
    "/v5/order/cancel-all",
    "/v5/position/set-leverage",
    "/v5/position/trading-stop",
    "/v5/position/switch-mode",
    "/v5/asset/withdraw",
    "/v5/asset/transfer",
    "/v5/asset/create-sub-member-transfer",
)

FORBIDDEN_MAINNET_HOSTS: frozenset[str] = frozenset(
    {
        "api.bybit.com",
        "api.bytick.com",
    }
)

DEMO_HOST = "api-demo.bybit.com"
TESTNET_HOST = "api-testnet.bybit.com"

DEMO_ENV_KEY = "BYBIT_DEMO_API_KEY"
DEMO_ENV_SECRET = "BYBIT_DEMO_API_SECRET"
MAINNET_ENV_KEY = "BYBIT_API_KEY"
MAINNET_ENV_SECRET = "BYBIT_API_SECRET"

# Module path prefixes classified for import-graph audit.
PUBLIC_ROUTE_PREFIXES: tuple[str, ...] = (
    "backend.api.market_public_routes",
    "backend.api.market_chart_routes",
    "backend.api.market_sector_routes",
    "backend.api.market_scanner_routes",
    "backend.api.market_intelligence_routes",
    "backend.api.nexus_market_data_routes",
)

PRIVATE_CORE_PREFIXES: tuple[str, ...] = (
    "backend.nexus_autonomy",
    "backend.nexus_learning",
    "backend.nexus_strategy_engine.lesson_seal",
)

EXECUTION_WRITE_MODULES: frozenset[str] = frozenset(
    {
        "backend.nexus_demo_execution.demo_write_client",
        "backend.nexus_research.demo_autonomous.write_adapter",
        "backend.nexus_research.demo_autonomous.write_transport",
        "backend.nexus_research.demo_autonomous.write_trace",
    }
)

LESSON_PRIVATE_MODULES: frozenset[str] = frozenset(
    {
        "backend.nexus_learning",
    }
)

SIMULATION_PREFIXES: tuple[str, ...] = (
    "backend.nexus_autonomy.execution_simulator_v1",
    "backend.nexus_autonomy.closed_loop_harness_v1",
    "backend.nexus_autonomy.closed_loop_harness_v1_1",
    "backend.nexus_autonomy.integration_spine_v1",
    "backend.nexus_autonomy.session_orchestrator_v1",
    "backend.nexus_autonomy.historical_integration_replay_v1",
)

# Private fields that must never serialize into public schemas.
PRIVATE_LESSON_FIELDS: frozenset[str] = frozenset(
    {
        "lesson_id",
        "immediate_safe_actions",
        "process_classification",
        "temporary_controls",
        "reflection_provider",
        "critic_provider",
        "raw_provider_prompt",
        "raw_provider_response",
    }
)

PRIVATE_STRATEGY_PARAM_FIELDS: frozenset[str] = frozenset(
    {
        "strategy_parameters",
        "strategy_params",
        "entry_threshold",
        "stop_loss_pct",
        "take_profit_pct",
        "leverage_target",
        "position_sizing_formula",
        "alpha_weights",
    }
)

SECRET_PATTERNS: tuple[str, ...] = (
    "api_key",
    "api_secret",
    "apisecret",
    "private_key",
    "x-bapi-api-key",
    "x-bapi-sign",
    "authorization",
    "bearer ",
    "sk-",
    "password",
)

RECOMMENDATIONS: frozenset[str] = frozenset(
    {
        "NEXUS_PRIVATE_SECURITY_BOUNDARY_V1_PASS",
        "NEXUS_PRIVATE_SECURITY_EXCHANGE_WRITE_PATH_EXPOSED",
        "NEXUS_PRIVATE_SECURITY_PUBLIC_PRIVATE_BOUNDARY_FAILED",
        "NEXUS_PRIVATE_SECURITY_CREDENTIAL_BOUNDARY_FAILED",
        "NEXUS_PRIVATE_SECURITY_PERSISTENCE_FAILED",
        "NEXUS_PRIVATE_SECURITY_CRITICAL_FINDINGS_REMAIN",
        "NEXUS_PRIVATE_SECURITY_IMPLEMENTATION_INVALID",
    }
)
