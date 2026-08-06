"""V17-C Silver Normalization — Symbol Identity constants."""
from __future__ import annotations

SCHEMA = "v17_silver_symbol_identity_v1"
PROGRAM_ID = "NEXUS_V17_SILVER_NORMALIZATION_SYMBOL_IDENTITY"
LANE = "V17-C"
LANE_NAME = "silver_normalization_symbol_identity"
BRANCH = "feature/v17-silver-symbol-identity"
IDENTITY_VERSION = "silver_identity_v1"

OWNED_PATHS = (
    "backend/nexus_silver_symbol_identity/",
    "tests/silver_symbol_identity/",
    "artifacts/readiness/immutable/v17_silver_symbol_identity/",
)

HARD_BANS = (
    "no_exchange_write",
    "no_mainnet_client",
    "no_real_money",
    "no_auto_integration_into_PR26",
    "no_auto_integration_into_PR27",
    "no_erase_delisted_instruments",
    "no_collapse_cross_exchange_symbols",
    "no_collapse_spot_perp_identity",
    "no_silent_rename_without_lineage",
    "no_drop_stablecoin_depeg_periods",
    "no_fixture_as_real_performance",
)

MARKET_TYPES = ("spot", "perp", "future", "options")
MARGIN_KINDS = ("linear", "inverse", "na")

# Canonical silver instrument identity fields (ordered).
CANONICAL_IDENTITY_FIELDS = (
    "canonical_asset_id",
    "canonical_instrument_id",
    "exchange",
    "exchange_symbol",
    "market_type",
    "quote_asset",
    "base_asset",
    "contract_multiplier",
    "margin_kind",
    "tick_size",
    "lot_size",
    "min_notional",
    "listing_time",
    "delisting_time",
    "contract_rule_version",
)

EVIDENCE_CLASS = "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
ARTIFACT_REL = "artifacts/readiness/immutable/v17_silver_symbol_identity"
SCHEMA_REL = f"{ARTIFACT_REL}/silver_symbol_identity.schema.json"

PASS_RECOMMENDATION = "PASS_LANE_V17_C_SILVER_SYMBOL_IDENTITY"
