"""V14-B Event Study Engine — blocked infrastructure surface.

Hard bans: no PR27 merge/deploy/WF/OOS/Demo/exchange write/mainnet/profit claims.
Real 14-day Event Study must remain REAL_EVENT_STUDY_BLOCKED.
"""
from __future__ import annotations

from backend.nexus_event_study.bootstrap import bootstrap_mean_ci, bootstrap_report
from backend.nexus_event_study.completeness import filter_by_completeness, path_completeness
from backend.nexus_event_study.constants import (
    ENGINE_STATUS,
    EVENT_DEFINITION_IDS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    REAL_EVENT_STUDY_EXECUTION,
    REAL_EVENT_STUDY_STATUS,
    SCHEMA,
)
from backend.nexus_event_study.definitions import definition_catalog, list_definitions, require_definition
from backend.nexus_event_study.engine import run_blocked_fixture_study, verify_deterministic_study
from backend.nexus_event_study.fixtures import build_synthetic_cohort, make_study_event
from backend.nexus_event_study.forensic_ro import (
    ForensicWriteAttemptError,
    forensic_campaign_probe,
    refuse_write,
)
from backend.nexus_event_study.grouping import summarize_groups
from backend.nexus_event_study.missing import classify_missing
from backend.nexus_event_study.outcomes import multi_horizon_outcomes, summarize_horizon_outcomes
from backend.nexus_event_study.overlap import exclude_overlapping
from backend.nexus_event_study.pit import filter_pit, prove_pit_excludes_future
from backend.nexus_event_study.windows import build_windows, describe_window_policy

__all__ = [
    "ENGINE_STATUS",
    "EVENT_DEFINITION_IDS",
    "ForensicWriteAttemptError",
    "HARD_BANS",
    "LANE",
    "LANE_NAME",
    "REAL_EVENT_STUDY_EXECUTION",
    "REAL_EVENT_STUDY_STATUS",
    "SCHEMA",
    "bootstrap_mean_ci",
    "bootstrap_report",
    "build_synthetic_cohort",
    "build_windows",
    "classify_missing",
    "definition_catalog",
    "describe_window_policy",
    "exclude_overlapping",
    "filter_by_completeness",
    "filter_pit",
    "forensic_campaign_probe",
    "list_definitions",
    "make_study_event",
    "multi_horizon_outcomes",
    "path_completeness",
    "prove_pit_excludes_future",
    "refuse_write",
    "require_definition",
    "run_blocked_fixture_study",
    "summarize_groups",
    "summarize_horizon_outcomes",
    "verify_deterministic_study",
]
