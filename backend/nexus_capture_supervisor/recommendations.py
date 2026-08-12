"""Automatic safe-stop + graceful restart recommendations (observe-only)."""
from __future__ import annotations

from typing import Any

from backend.nexus_capture_supervisor.constants import (
    OPS_ROLE,
    RESTART_EXECUTION_OWNER,
    SCHEMA_RECOMMENDATION,
    STOP_EXECUTION_OWNER,
)
from backend.nexus_capture_supervisor.util import severity_rank, utc_stamp


def build_recommendations(*, observation: dict[str, Any]) -> dict[str, Any]:
    """Derive safe-stop / restart recommendations without executing them."""
    findings: list[dict[str, Any]] = []
    for key in (
        "process_liveness",
        "ws_health",
        "partition_accounting",
        "clock_heartbeat",
        "storage",
        "manifest_sampling",
        "open_tail",
        "duplicate_writer",
    ):
        block = observation.get(key) or {}
        findings.extend(block.get("findings") or [])

    critical = [f for f in findings if f.get("severity") == "CRITICAL"]
    high = [f for f in findings if f.get("severity") == "HIGH"]

    safe_stop_required = bool(critical) or (
        (observation.get("storage") or {}).get("status") == "STOP_REQUIRED"
    )
    if (observation.get("duplicate_writer") or {}).get("status") == "DUPLICATE_SUSPECTED":
        safe_stop_required = True
    if (observation.get("process_liveness") or {}).get("status") == "DOWN":
        safe_stop_required = True

    reasons: list[str] = []
    for f in sorted(critical + high, key=lambda x: severity_rank(str(x.get("severity")))):
        reasons.append(str(f.get("code")))
    reasons = list(dict.fromkeys(reasons))

    restart_recommended = False
    restart_mode = None
    if safe_stop_required:
        # Dead process or WS gap / duplicate → graceful restart after fence
        codes = set(reasons)
        if codes & {
            "PROCESS_PARENT_DEAD",
            "PROCESS_WORKER_DEAD",
            "WS_CHECKPOINT_STALE_CRITICAL",
            "WS_IMPLIED_DOWN_PROCESS",
            "DUPLICATE_PARTITION_PATHS",
            "LAUNCH_HEALTH_PID_MISMATCH",
        }:
            restart_recommended = True
            restart_mode = "GRACEFUL_AFTER_OPEN_TAIL_FENCE"
        if codes & {"DISK_FLOOR_BREACH", "HARD_CAP_BREACH", "CHECKSUM_SAMPLE_MISMATCH"}:
            # Stop and hold — do not auto-restart into bad disk/integrity
            restart_recommended = False
            restart_mode = "HOLD_NO_AUTO_RESTART"

    actions = [
        "persist_supervisor_observation",
        "notify_coordinator",
    ]
    forbidden = [
        "supervisor_executes_live_stop",
        "supervisor_executes_restart",
        "exchange_write",
        "event_study_execution",
        "raw_partition_rewrite",
        "open_tail_deletion",
        "dual_writer_start",
    ]

    if safe_stop_required:
        actions.extend(
            [
                "recommend_block_new_segment",
                "recommend_request_collector_stop",
                "recommend_persist_checkpoint",
                "recommend_retain_partitions",
            ]
        )
    if restart_recommended:
        actions.extend(
            [
                "recommend_fence_open_tails",
                "recommend_single_writer_restart",
                "recommend_verify_exclusive_partition_ids",
            ]
        )

    return {
        "schema": SCHEMA_RECOMMENDATION,
        "observed_at": utc_stamp(),
        "ops_role": OPS_ROLE,
        "stop_execution_owner": STOP_EXECUTION_OWNER,
        "restart_execution_owner": RESTART_EXECUTION_OWNER,
        "safe_stop_required": safe_stop_required,
        "safe_stop_executed": False,
        "restart_recommended": restart_recommended,
        "restart_executed": False,
        "restart_mode": restart_mode,
        "primary_reason": reasons[0] if reasons else None,
        "reasons": reasons,
        "critical_count": len(critical),
        "high_count": len(high),
        "actions": actions,
        "forbidden_actions": forbidden,
        "exchange_write_attempt_count": 0,
        "event_study_readiness_status": "NOT_READY",
    }
