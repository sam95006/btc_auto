"""V14-G Lesson Prevention Proof V2 — mechanics fixtures + blocked real policy gate."""
from __future__ import annotations

from backend.nexus_lesson_prevention_v2.classification import (
    assert_loss_not_auto_bad,
    classify_from_evidence,
    error_signature,
    migrate_classification,
)
from backend.nexus_lesson_prevention_v2.constants import (
    ARTIFACT_REL,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    SCHEMA,
)
from backend.nexus_lesson_prevention_v2.harness import (
    run_lesson_prevention_v2,
    write_immutable_artifacts,
    write_runtime_status,
)

__all__ = [
    "SCHEMA",
    "LANE",
    "LANE_NAME",
    "BRANCH",
    "OWNED_PATHS",
    "HARD_BANS",
    "ARTIFACT_REL",
    "classify_from_evidence",
    "migrate_classification",
    "assert_loss_not_auto_bad",
    "error_signature",
    "run_lesson_prevention_v2",
    "write_immutable_artifacts",
    "write_runtime_status",
]
