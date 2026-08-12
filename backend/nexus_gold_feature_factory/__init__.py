"""V17-G Gold Feature Factory — reproducible gold-layer feature surface.

Hard bans: silent forward fill, future price labels, unmarked missing,
multiple authoritative formulas for the same name. Fixture-only this round.
No exchange/mainnet/PR26/27/report edits.
"""
from __future__ import annotations

from backend.nexus_gold_feature_factory.catalog import (
    feature_catalog,
    formula_authority_map,
    require_feature,
)
from backend.nexus_gold_feature_factory.constants import (
    FEATURE_IDS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    REQUIRED_METADATA_FIELDS,
    SCHEMA,
)
from backend.nexus_gold_feature_factory.factory import (
    compute_all_features,
    compute_feature,
    fingerprint_bundle,
    prove_pit_excludes_future,
    run_factory_guards,
    verify_deterministic_replay,
)
from backend.nexus_gold_feature_factory.fixtures import build_synthetic_market
from backend.nexus_gold_feature_factory.guards import (
    FeatureFactoryBanError,
    reject_duplicate_authority,
)

__all__ = [
    "FEATURE_IDS",
    "HARD_BANS",
    "LANE",
    "LANE_NAME",
    "REQUIRED_METADATA_FIELDS",
    "SCHEMA",
    "FeatureFactoryBanError",
    "build_synthetic_market",
    "compute_all_features",
    "compute_feature",
    "feature_catalog",
    "fingerprint_bundle",
    "formula_authority_map",
    "prove_pit_excludes_future",
    "reject_duplicate_authority",
    "require_feature",
    "run_factory_guards",
    "verify_deterministic_replay",
]
