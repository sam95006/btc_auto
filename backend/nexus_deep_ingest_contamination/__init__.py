"""V17 deep engineering — ingest recovery + dataset contamination."""
from __future__ import annotations

from backend.nexus_deep_ingest_contamination.archive_recovery import CorruptArchiveRecovery
from backend.nexus_deep_ingest_contamination.campaign import run_campaign
from backend.nexus_deep_ingest_contamination.constants import (
    COVERAGE_AREAS,
    LANE,
    LANE_NAME,
    SCHEMA,
)
from backend.nexus_deep_ingest_contamination.duplicate_ingest import DuplicateDatasetIngestor
from backend.nexus_deep_ingest_contamination.provider_failover import (
    ProviderFailoverSimulator,
    build_default_failover_proofs,
)
from backend.nexus_deep_ingest_contamination.redteam import run_ingest_contamination_redteam
from backend.nexus_deep_ingest_contamination.resource_profile import run_bounded_resource_smoke
from backend.nexus_deep_ingest_contamination.revision_conflict import RevisionConflictHarness
from backend.nexus_deep_ingest_contamination.split_contamination import (
    run_deep_split_contamination_attacks,
)

__all__ = [
    "COVERAGE_AREAS",
    "CorruptArchiveRecovery",
    "DuplicateDatasetIngestor",
    "LANE",
    "LANE_NAME",
    "ProviderFailoverSimulator",
    "RevisionConflictHarness",
    "SCHEMA",
    "build_default_failover_proofs",
    "run_bounded_resource_smoke",
    "run_campaign",
    "run_deep_split_contamination_attacks",
    "run_ingest_contamination_redteam",
]
