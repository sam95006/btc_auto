"""V17-C Silver Normalization — Symbol Identity.

Canonical instrument identity for the silver layer:
cross-exchange symbol disambiguation, spot≠perp, contract-rule versions,
delisted retention, rename lineage, and stablecoin depeg period retention.

Fixture / offline only — no exchange write, no mainnet.
"""
from __future__ import annotations

from backend.nexus_silver_symbol_identity.artifacts import write_immutable_artifacts
from backend.nexus_silver_symbol_identity.constants import (
    ARTIFACT_REL,
    BRANCH,
    CANONICAL_IDENTITY_FIELDS,
    HARD_BANS,
    IDENTITY_VERSION,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PROGRAM_ID,
    SCHEMA,
    SCHEMA_REL,
)
from backend.nexus_silver_symbol_identity.depeg import (
    assert_depeg_periods_retained,
    attach_depeg_period,
    make_depeg_period,
    retained_depeg_periods,
)
from backend.nexus_silver_symbol_identity.fixtures import build_fixture_registry, fixture_catalog
from backend.nexus_silver_symbol_identity.hard_bans import (
    HardBanViolation,
    assert_hard_bans_declared,
    refuse_exchange_write,
    refuse_mainnet,
    refuse_pr_integration,
)
from backend.nexus_silver_symbol_identity.identity import (
    build_canonical_asset_id,
    build_canonical_instrument_id,
    instruments_are_same_instrument,
    instruments_share_symbol_string,
)
from backend.nexus_silver_symbol_identity.lineage import (
    apply_symbol_rename,
    detect_silent_rename,
)
from backend.nexus_silver_symbol_identity.normalize import normalize_raw_instrument
from backend.nexus_silver_symbol_identity.registry import SilverInstrumentRegistry
from backend.nexus_silver_symbol_identity.schema import build_schema, validate_silver_instrument

__all__ = [
    "SCHEMA",
    "SCHEMA_REL",
    "ARTIFACT_REL",
    "PROGRAM_ID",
    "LANE",
    "LANE_NAME",
    "BRANCH",
    "IDENTITY_VERSION",
    "OWNED_PATHS",
    "HARD_BANS",
    "CANONICAL_IDENTITY_FIELDS",
    "build_canonical_asset_id",
    "build_canonical_instrument_id",
    "instruments_are_same_instrument",
    "instruments_share_symbol_string",
    "normalize_raw_instrument",
    "build_schema",
    "validate_silver_instrument",
    "SilverInstrumentRegistry",
    "apply_symbol_rename",
    "detect_silent_rename",
    "make_depeg_period",
    "attach_depeg_period",
    "retained_depeg_periods",
    "assert_depeg_periods_retained",
    "build_fixture_registry",
    "fixture_catalog",
    "HardBanViolation",
    "assert_hard_bans_declared",
    "refuse_exchange_write",
    "refuse_mainnet",
    "refuse_pr_integration",
    "write_immutable_artifacts",
]
