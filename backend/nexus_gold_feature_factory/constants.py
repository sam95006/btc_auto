"""V17-G Gold Feature Factory — constants and hard bans."""
from __future__ import annotations

SCHEMA = "FOUNDER_V17_G_GOLD_FEATURE_FACTORY"
FEATURE_SCHEMA_VERSION = "gold_feature_factory_v17_g_1"
CATALOG_VERSION = "v17_g_feature_catalog_1"
LANE = "V17-G"
LANE_NAME = "GOLD_FEATURE_FACTORY"
BRANCH = "feature/v17-gold-feature-factory"
BASE_COMMIT = "66a0f7827d5709fc09bc8c7495e93a4089eb28de"

FEATURE_VERSION = "1.0.0"
DEFAULT_LOOKBACK_BARS = 20
DEFAULT_STALE_AFTER_MS = 120_000

# Single authoritative name set — one formula per name, no aliases as authorities.
FEATURE_IDS = (
    "trend",
    "volatility",
    "liquidity",
    "spread",
    "turnover",
    "funding",
    "open_interest",
    "liquidation",
    "crowding",
    "order_flow",
    "cross_asset",
    "session",
    "event_risk",
    "market_breadth",
    "stablecoin_stress",
    "data_trust",
)

REQUIRED_METADATA_FIELDS = (
    "feature_version",
    "source_lineage",
    "as_of",
    "available_at",
    "lookback",
    "normalization",
    "missing_policy",
    "license_scope",
    "calculation_hash",
)

# Explicit missing policies — never silent / unmarked.
MISSING_POLICIES = (
    "MARK_UNAVAILABLE",
    "EXCLUDE_WITH_REASON",
    "PROPAGATE_QUALITY",
)

HARD_BANS = {
    "silent_forward_fill": False,
    "future_price_labels": False,
    "unmarked_missing": False,
    "multiple_authoritative_formulas_same_name": False,
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "pr26_merge": False,
    "pr27_merge": False,
    "report_edit": False,
}

OWNED_PATHS = [
    "backend/nexus_gold_feature_factory",
    "tests/test_gold_feature_factory_v17.py",
    "tools/research/run_gold_feature_factory_v17.py",
]

EVIDENCE_CLASSIFICATION = "fixture"
