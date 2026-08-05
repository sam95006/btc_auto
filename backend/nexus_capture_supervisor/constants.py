"""V14-A Live Capture Integrity Supervisor — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v14_a_live_capture_integrity_supervisor"
SCHEMA_STATUS = "v14_a_capture_supervisor_status"
SCHEMA_PASS1 = "v14_a_capture_supervisor_pass1"
SCHEMA_PASS2 = "v14_a_capture_supervisor_pass2"
SCHEMA_BOTH = "v14_a_capture_supervisor_both_passes"
SCHEMA_SECRET = "v14_a_capture_supervisor_secret_scan"
SCHEMA_RECOMMENDATION = "v14_a_capture_supervisor_recommendation"

LANE = "V14-A"
LANE_NAME = "LIVE_CAPTURE_INTEGRITY_SUPERVISOR"
BRANCH = "feature/v14-live-capture-integrity-supervisor"
BASE_COMMIT = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"
ARTIFACT_REL = "artifacts/readiness/immutable/v14_capture_supervisor"
RUNTIME_STATUS_NAME = "v14_a_status.json"

CAMPAIGN_ID = "ms_accum_v13_integrity_14d"
DEFAULT_RUNTIME = r"D:\NEXUS_RUNTIME"
DEFAULT_DISK_ROOT = "D:\\"

GIB = 1024**3
STORAGE_FLOOR_BYTES = 100 * GIB
HARD_CAP_BYTES = 40 * GIB
SOFT_CAP_BYTES = int(HARD_CAP_BYTES * 0.8)

TARGET_CALENDAR_DAYS = 14
MIN_SYMBOL_COUNT = 25
FAMILIES = ("AGGRESSIVE_TRADE_FLOW", "LIQUIDATION_EVENTS")
EXPECTED_HOURS_PER_DAY = 24

# Observation thresholds (explicit — never silently widen).
PROCESS_STALE_SECONDS = 300
CHECKPOINT_STALE_SECONDS = 600
WS_GAP_WARN_SECONDS = 120
WS_GAP_CRITICAL_SECONDS = 600
HEARTBEAT_STALE_SECONDS = 180
OPEN_TAIL_STALE_SECONDS = 3600
STORAGE_VELOCITY_SAMPLE_SECONDS = 60
DISK_PROJECTION_HORIZON_HOURS = 24
MANIFEST_SAMPLE_MAX = 32
CLOCK_SKEW_WARN_MS = 5_000
CLOCK_SKEW_CRITICAL_MS = 60_000
CLOCK_ROLLBACK_TOLERANCE_MS = 0

# Supervisor never owns live capture stop/restart execution.
OPS_ROLE = "observe_recommend_only"
STOP_EXECUTION_OWNER = "local_Coordinator"
RESTART_EXECUTION_OWNER = "local_Coordinator"

HARD_BANS: tuple[str, ...] = (
    "no_PR27_merge",
    "no_deploy",
    "no_WF_OOS",
    "no_Demo_Shadow",
    "no_exchange_write",
    "no_mainnet",
    "no_real_money",
    "no_V13A_collector_modification",
    "no_Event_Study_execution",
    "no_auto_integrate_V13_V14_parent",
    "no_live_stop_execution_from_supervisor",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_capture_supervisor",
    "tools/operations/capture_supervisor",
    "tests/capture_supervisor",
    ARTIFACT_REL,
)

FORBIDDEN_LOG_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "token",
        "private_key",
        "authorization",
        "bybit_api_key",
        "bybit_api_secret",
        "account_balance",
        "wallet_address",
        "trading_credentials",
    }
)

EVENT_STUDY_MUST_REMAIN = "NOT_READY"
