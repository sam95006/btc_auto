"""V17-D Point-in-Time and Revision Control — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v17_d_pit_revision_control_v1"
SCHEMA_VERSION = "v1.0.0"
PACKAGE = "backend.nexus_pit_revision_v17"
LANE = "V17-D"
LANE_NAME = "POINT_IN_TIME_AND_REVISION_CONTROL"
BRANCH = "feature/v17-point-in-time-revision"
ARTIFACT_REL = "artifacts/readiness/immutable/v17_pit_revision"
BASE_COMMIT = "66a0f7827d5709fc09bc8c7495e93a4089eb28de"
EVIDENCE_PATH = r"D:\NEXUS_RUNTIME\evidence_coordinator\v17_d_pit_revision.json"

# Dual-time axes (Founder V17-D).
TIME_AXES: tuple[str, ...] = (
    "event_time",
    "available_time",
    "revision_time",
    "ingest_time",
)

RECORD_KINDS: tuple[str, ...] = (
    "OBSERVATION",
    "LABEL",
    "BACKFILL",
    "LATE_ARRIVING",
)

QUERY_STATUSES: tuple[str, ...] = (
    "AVAILABLE",
    "UNAVAILABLE_AT_TIME",
    "REJECTED_MISSING_AS_KNOWN_AT",
    "REJECTED_TODAY_REVISION_FOR_PAST_BACKTEST",
    "REJECTED_FUTURE_LEAKAGE",
)

HARD_BANS: tuple[str, ...] = (
    "no_today_revision_for_past_backtest",
    "no_research_query_without_as_known_at",
    "no_future_leakage",
    "no_unavailable_at_time_silent_fill",
    "no_real_money",
    "no_mainnet",
    "no_exchange_write",
    "no_formal_wf",
    "no_oos_claims",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
    "no_status_json_lane_artifact",
    "no_auto_integrate",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_pit_revision_v17/",
    "tests/pit_revision_v17/",
    ARTIFACT_REL + "/",
    "tools/research/run_pit_revision_v17.py",
)

BANNED_CLAIM_FRAGMENTS: tuple[str, ...] = (
    "formal walk-forward complete",
    "formal WF complete",
    "oos sealed and consumed",
    "production ready",
    "mainnet enabled",
    "exchange write enabled",
)

CONTROL_FIXTURE_LABEL = "CONTROL_FIXTURE_NOT_REAL_MARKET_DATA"
NON_CLAIMS: tuple[str, ...] = (
    "No formal Walk-Forward executed",
    "No OOS consumption or sealed OOS metrics claimed",
    "No exchange/mainnet/real-money capability",
    "Synthetic fixtures only — not live market ingestion",
)
