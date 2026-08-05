"""PUB2-B — Public V2 Live Data End-to-End Binding constants."""
from __future__ import annotations

SCHEMA_VERSION = "public_v2_live_binding_v1"
PACKAGE = "backend.nexus_public_v2_live_binding"
LANE = "PUB2-B"
LANE_NAME = "LIVE_DATA_END_TO_END_BINDING"
BRANCH = "feature/public-v2-live-data-e2e-binding"
BASE_COMMIT = "5e93f677ece9f283aeade98657b5e3d5736991b5"
PROGRAM_ID = "NEXUS_PUBLIC_V2_LIVE_DATA_E2E_BINDING"

MODE_LIVE = "LIVE"

# Every visible value must carry these lineage / honesty keys.
BINDING_REQUIRED_KEYS: tuple[str, ...] = (
    "source",
    "field",
    "unit",
    "as_of",
    "retrieved_at",
    "freshness",
    "completeness",
    "quality",
    "lineage",
    "fallback",
)

REQUIRED_COUNTERS: tuple[str, ...] = (
    "hardcoded_live_value_count",
    "fabricated_live_value_count",
    "stale_without_indicator_count",
    "unavailable_shown_as_zero_count",
)

HARD_BANS: tuple[str, ...] = (
    "no_PR26_merge",
    "no_PR27_merge",
    "no_private_core_exposure",
    "no_exchange_write",
    "no_demo_merged_as_live",
    "no_fabricated_live_values",
    "no_hardcoded_live_values",
    "no_stale_without_indicator",
    "no_unavailable_shown_as_zero",
    "no_customer_trading",
    "no_mainnet_trading",
    "no_real_money",
    "no_status_json_artifacts",
    "no_report_edit",
    "local_staging_only",
)

FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "backend.trading",
    "backend.wallet",
    "backend.portfolio",
    "backend.fleets",
    "backend.learning",
    "backend.nexus_research",
    "backend.nexus_demo_execution",
    "backend.nexus_autonomy",
    "backend.nexus_execution",
    "backend.nexus_strategy_engine",
    "backend.nexus_learning",
    "backend.risk",
    "ccxt",
    "pybit",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_public_v2_live_binding",
    "tools/public_v2/run_live_data_e2e_binding_gate.py",
    "tests/public_v2_live_binding",
    "frontend/src/public_v2_live_binding",
)

# Frontend surfaces that must not hardcode LIVE numeric values.
MEMBER_UI_SCAN_GLOBS: tuple[str, ...] = (
    "frontend/src/pages/member/**/*.tsx",
    "frontend/src/pages/member/**/*.ts",
    "frontend/src/member/**/*.tsx",
    "frontend/src/member/**/*.ts",
    "frontend/src/public_v2_live_binding/**/*.tsx",
    "frontend/src/public_v2_live_binding/**/*.ts",
)

PASS_RECOMMENDATION = "NEXUS_PUBLIC_V2_LIVE_DATA_E2E_BINDING_PASS"
FAIL_RECOMMENDATION = "NEXUS_PUBLIC_V2_LIVE_DATA_E2E_BINDING_FAIL"

EXCHANGE_WRITE_MARKERS: tuple[str, ...] = (
    "EXCHANGE_WRITE=True",
    "MAINNET=True",
    "REAL_MONEY=True",
    "place_order",
    "submit_order",
    "create_order",
    "execute_trade",
)
