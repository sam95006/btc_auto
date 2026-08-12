"""V17-A Data Source and License Registry.

Machine-readable registry of legal data sources with license posture and
status gates. Hard-bans paywalled Glassnode/CoinGlass/Messari scrapes and
auth/rate-limit bypass. LICENSE_REVIEW_REQUIRED allows adapter contracts
only — no training, no public display, no authorization claims.
"""
from __future__ import annotations

from backend.nexus_data_source_registry.constants import (
    ARTIFACT_REL,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    REQUIRED_SOURCE_FIELDS,
    SCHEMA,
    SCHEMA_REL,
    SCHEMA_VERSION,
    SOURCE_SCHEMA,
    SOURCE_STATUSES,
)
from backend.nexus_data_source_registry.fixtures import (
    build_fixture_registry_document,
    fixture_sources,
    write_fixture_artifact,
)
from backend.nexus_data_source_registry.registry import (
    DataSourceRegistry,
    DataSourceRegistryError,
)
from backend.nexus_data_source_registry.schema import (
    build_schema,
    build_source_schema,
    validate_registry_document,
    validate_source_record,
    write_schema_artifact,
)

__all__ = [
    "ARTIFACT_REL",
    "BRANCH",
    "HARD_BANS",
    "LANE",
    "LANE_NAME",
    "OWNED_PATHS",
    "REQUIRED_SOURCE_FIELDS",
    "SCHEMA",
    "SCHEMA_REL",
    "SCHEMA_VERSION",
    "SOURCE_SCHEMA",
    "SOURCE_STATUSES",
    "DataSourceRegistry",
    "DataSourceRegistryError",
    "build_fixture_registry_document",
    "build_schema",
    "build_source_schema",
    "fixture_sources",
    "validate_registry_document",
    "validate_source_record",
    "write_fixture_artifact",
    "write_schema_artifact",
]
