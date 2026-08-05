"""V12-F Closed-Loop Red Team — constants and owned-path declarations."""
from __future__ import annotations

SCHEMA = "v12_closed_loop_redteam"
PROGRAM_ID = "NEXUS_V12_CLOSED_LOOP_REDTEAM"
LANE = "V12-F"
BRANCH = "feature/v12-closed-loop-redteam"
BASE_HEAD = "e4e96299840da2e5152cf2850135cebc67d66cd0"

PASS_RECOMMENDATION = "NEXUS_V12_CLOSED_LOOP_REDTEAM_PASS"
FAIL_RECOMMENDATION = "NEXUS_V12_CLOSED_LOOP_REDTEAM_CRITICAL_FINDINGS"
INVALID_RECOMMENDATION = "NEXUS_V12_CLOSED_LOOP_REDTEAM_IMPLEMENTATION_INVALID"

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_autonomy/closed_loop_redteam_v12/",
    "tools/research/run_closed_loop_redteam_v12.py",
    "tests/test_closed_loop_redteam_v12.py",
    "artifacts/readiness/immutable/v12_closed_loop_redteam/",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "backend/nexus_demo_execution/",
    "G:/",
    "PR27",
    "deploy/",
)

HARD_BANS: tuple[str, ...] = (
    "no_auto_integration_into_PR27",
    "no_demo_orders",
    "no_exchange_write",
    "no_mainnet_client",
    "no_merge",
    "no_deploy",
)

SCENARIO_IDS: tuple[str, ...] = (
    "duplicate_candidate_decision_intent",
    "partial_fill_crash",
    "exit_before_position_snapshot",
    "reflection_before_exit",
    "lesson_before_verified_reflection",
    "checkpoint_rollback",
    "ledger_fork",
    "oos_authorization_spoof",
    "exchange_write_attempts",
    "mainnet_profile_confusion",
)

LABEL = "CLOSED_LOOP_REDTEAM_CONTROL_NOT_REAL_TRADING"
EXECUTION_MODE = "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE"

RUNTIME_MATRIX_PATH = "D:\\NEXUS_RUNTIME\\v12_readiness_matrix.json"
RUNTIME_LANE_STATUS_PATH = "D:\\NEXUS_RUNTIME\\v12_f_closed_loop_redteam_status.json"
