"""V14-B Event Study Engine — constants, hard bans, and block flags."""
from __future__ import annotations

SCHEMA = "FOUNDER_V14_B_EVENT_STUDY_ENGINE"
ENGINE_SCHEMA_VERSION = "event_study_engine_v14_b_1"
LANE = "V14-B"
LANE_NAME = "EVENT_STUDY_ENGINE"
BRANCH = "feature/v14-event-study-engine"
BASE_COMMIT = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"

# Required dual status — engine may be ready while real study remains blocked.
ENGINE_STATUS = "ENGINE_READY"
REAL_EVENT_STUDY_STATUS = "REAL_EVENT_STUDY_BLOCKED"
REAL_EVENT_STUDY_EXECUTION = False

# Old campaign: read-only forensic only.
REFERENCE_CAMPAIGN_ID = "ms_accum_v7_bounded_24h"
REFERENCE_FINALIZER_ARTIFACT_DIR = (
    "artifacts/readiness/immutable/microstructure_campaign_finalizer_v1_real_ms_accum_v7"
)

# Default study geometry (bars / ms depending on caller context).
DEFAULT_PRE_WINDOW_BARS = 8
DEFAULT_POST_WINDOW_BARS = 16
DEFAULT_CONTROL_WINDOW_BARS = 16
DEFAULT_OVERLAP_EXCLUSION_BARS = 8
DEFAULT_HORIZONS = (1, 4, 8, 16, 32)
DEFAULT_BOOTSTRAP_REPLICATES = 200
DEFAULT_BOOTSTRAP_BLOCK = 4
DEFAULT_BOOTSTRAP_SEED = 14
DEFAULT_FEE_BPS = 5.5
DEFAULT_SLIP_BPS = 2.0
DEFAULT_MIN_COMPLETENESS = 0.85
DEFAULT_MIN_EVENTS_PER_GROUP = 3

EVENT_DEFINITION_IDS = (
    "aggressive_flow_burst",
    "liquidation_cascade_onset",
    "spread_shock",
    "funding_dislocation",
    "basis_dislocation",
    "oi_step_change",
    "absorption_print",
    "liquidity_withdrawal",
)

HARD_BANS = {
    "pr27_merge": False,
    "deploy": False,
    "formal_walk_forward": False,
    "oos_execution": False,
    "demo_orders": False,
    "exchange_write": False,
    "mainnet": False,
    "real_money": False,
    "profitability_claims": False,
    "real_14d_event_study": False,
    "auto_integrate": False,
}

OWNED_PATHS = [
    "backend/nexus_event_study",
    "tools/research/event_study",
    "tests/event_study",
    "artifacts/readiness/immutable/v14_event_study_engine",
]

# Hold conditions for lifting REAL_EVENT_STUDY_BLOCKED (not satisfied in this lane).
REAL_STUDY_HOLD_CONDITIONS = {
    "calendar_days": 14,
    "complete_UTC_day_coverage": True,
    "symbol_diversity": 25,
    "liquidation_event_count": 500,
    "integrity_status": "PASS",
    "Founder_authorization": True,
    "engine_status_required": "ENGINE_READY",
}
