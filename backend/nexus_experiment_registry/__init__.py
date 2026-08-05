"""V14-J Experiment Registry — Founder-private immutable research registry.

Binds lineage, checksums, versions, seeds, result hashes, parent links,
and duplicate / silent-cherry-pick detection. Simulated-only; no OOS
consumption, no Demo/exchange, no auto-integration.
"""
from __future__ import annotations

from backend.nexus_experiment_registry.campaign import run_experiment_registry_campaign
from backend.nexus_experiment_registry.constants import (
    HARD_BAN_FLAGS,
    HARD_BANS,
    IDENTITY_FIELDS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    RECORD_SCHEMA,
    REGISTRY_SCHEMA,
    SCHEMA,
)
from backend.nexus_experiment_registry.hashing import (
    checksum_lineage,
    checksum_parameters,
    checksum_universe,
    sha256_hex,
)
from backend.nexus_experiment_registry.record import (
    ExperimentRecordError,
    build_experiment_record,
    compute_identity_fingerprint,
    compute_record_hash,
    verify_experiment_record,
)
from backend.nexus_experiment_registry.registry import (
    ExperimentRegistryError,
    ImmutableExperimentRegistry,
)
from backend.nexus_experiment_registry.versions import resolve_version_pins

__all__ = [
    "HARD_BAN_FLAGS",
    "HARD_BANS",
    "IDENTITY_FIELDS",
    "LANE",
    "LANE_NAME",
    "OWNED_PATHS",
    "RECORD_SCHEMA",
    "REGISTRY_SCHEMA",
    "SCHEMA",
    "ExperimentRecordError",
    "ExperimentRegistryError",
    "ImmutableExperimentRegistry",
    "build_experiment_record",
    "checksum_lineage",
    "checksum_parameters",
    "checksum_universe",
    "compute_identity_fingerprint",
    "compute_record_hash",
    "resolve_version_pins",
    "run_experiment_registry_campaign",
    "sha256_hex",
    "verify_experiment_record",
]
