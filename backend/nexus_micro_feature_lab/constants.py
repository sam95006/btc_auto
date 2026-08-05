"""V13-E Microstructure Feature Lab — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V13_E_MICROSTRUCTURE_FEATURE_LAB"
FEATURE_SCHEMA_VERSION = "micro_feature_lab_v13_e_1"
CATALOG_VERSION = "v13_e_feature_catalog_1"
LANE = "V13-E"
LANE_NAME = "MICROSTRUCTURE_FEATURE_LAB"
BRANCH = "feature/v13-microstructure-feature-lab"
BASE_COMMIT = "abd2195ef6d79f609dd261b5e9c5402599625a64"

# Default feature window (exchange time).
DEFAULT_WINDOW_MS = 60_000
DEFAULT_STALE_AFTER_MS = 120_000

# Old campaign: read-only forensic only — never seal/modify raw partitions.
REFERENCE_CAMPAIGN_ID = "ms_accum_v7_bounded_24h"
REFERENCE_FINALIZER_ARTIFACT_DIR = (
    "artifacts/readiness/immutable/microstructure_campaign_finalizer_v1_real_ms_accum_v7"
)

FEATURE_IDS = (
    "aggressive_buy_sell_imbalance",
    "trade_intensity",
    "trade_size_distribution",
    "liquidation_intensity",
    "liquidation_clustering",
    "flow_persistence",
    "flow_reversal",
    "price_impact",
    "absorption_proxy",
    "vol_adjusted_flow",
    "cross_symbol_flow",
    "regime_context",
)

HARD_BANS = {
    "predictive_edge_claims": False,
    "silent_seal_or_modify_old_raw_partitions": False,
    "event_study": False,
    "demo_orders": False,
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "pr27_merge": False,
    "formal_walk_forward": False,
    "oos_execution": False,
}

OWNED_PATHS = [
    "backend/nexus_micro_feature_lab",
    "tools/research/run_microstructure_feature_lab_v13.py",
    "tests/test_microstructure_feature_lab_v13.py",
    "artifacts/readiness/immutable/v13_microstructure_feature_lab",
]
