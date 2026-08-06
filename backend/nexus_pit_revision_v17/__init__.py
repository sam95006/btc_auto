"""V17-D Point-in-Time and Revision Control.

Dual-time model: event_time, available_time, revision_time, ingest_time.
Research queries require AS_KNOWN_AT. Today's tip revision is banned for past
backtests. Future-leakage redteam must report zero survivors.

Hard bans: no report edit, no exchange/mainnet, no PR26/27, no formal WF/OOS claims.
"""
from __future__ import annotations

from backend.nexus_pit_revision_v17.constants import (
    ARTIFACT_REL,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    NON_CLAIMS,
    OWNED_PATHS,
    SCHEMA,
    SCHEMA_VERSION,
    TIME_AXES,
)
from backend.nexus_pit_revision_v17.fixtures import build_revision_catalog, fixture_summary
from backend.nexus_pit_revision_v17.harness import (
    evaluate_pit_revision_control,
    run_pit_revision_lab,
    write_immutable_artifacts,
)
from backend.nexus_pit_revision_v17.redteam import run_future_leakage_redteam
from backend.nexus_pit_revision_v17.store import (
    PitRevisionStore,
    prove_pit_visibility,
    research_query,
)
from backend.nexus_pit_revision_v17.types import (
    DualTimeStamp,
    QueryResult,
    ResearchQuery,
    RevisionRecord,
)

__all__ = [
    "ARTIFACT_REL",
    "BRANCH",
    "HARD_BANS",
    "LANE",
    "LANE_NAME",
    "NON_CLAIMS",
    "OWNED_PATHS",
    "SCHEMA",
    "SCHEMA_VERSION",
    "TIME_AXES",
    "DualTimeStamp",
    "PitRevisionStore",
    "QueryResult",
    "ResearchQuery",
    "RevisionRecord",
    "build_revision_catalog",
    "evaluate_pit_revision_control",
    "fixture_summary",
    "prove_pit_visibility",
    "research_query",
    "run_future_leakage_redteam",
    "run_pit_revision_lab",
    "write_immutable_artifacts",
]
