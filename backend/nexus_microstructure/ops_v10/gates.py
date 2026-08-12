"""Capture start gates for Microstructure Operations V10."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.nexus_microstructure.ops_v10.constants import (
    MIN_FREE_DISK_BYTES_FOR_NEW_SEGMENT,
    SCHEMA,
)
from backend.nexus_microstructure.storage_budget_v10 import check_minimum_free_disk


@dataclass
class CaptureStartGatesV10:
    """Immutable snapshot of gate evaluation inputs."""

    d_free_space_ok: bool
    previous_campaign_finalized: bool
    storage_cap_configured: bool
    minimum_free_disk_controller_pass: bool
    enable_live_capture: bool = False

    def decision(self) -> str:
        all_pass = (
            self.d_free_space_ok
            and self.previous_campaign_finalized
            and self.storage_cap_configured
            and self.minimum_free_disk_controller_pass
        )
        if not all_pass:
            return "BLOCK_START"
        if not self.enable_live_capture:
            return "DRY_RUN_ONLY"
        return "ALLOW_START"


def evaluate_capture_start_gates(
    *,
    disk_root: str = "D:\\",
    minimum_free_disk_bytes: int = MIN_FREE_DISK_BYTES_FOR_NEW_SEGMENT,
    previous_campaign_finalized: bool,
    storage_cap_configured: bool,
    enable_live_capture: bool = False,
    free_disk_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate all gates required before a new bounded capture segment may begin."""
    free_report = free_disk_override or check_minimum_free_disk(
        disk_root,
        minimum_free_disk_bytes=minimum_free_disk_bytes,
    )
    gates = CaptureStartGatesV10(
        d_free_space_ok=bool(free_report.get("passed")),
        previous_campaign_finalized=bool(previous_campaign_finalized),
        storage_cap_configured=bool(storage_cap_configured),
        minimum_free_disk_controller_pass=bool(free_report.get("passed")),
        enable_live_capture=bool(enable_live_capture),
    )
    decision = gates.decision()
    gate_results = {
        "d_free_space_ge_30_gib": {
            "required": True,
            "passed": gates.d_free_space_ok,
            "detail": free_report,
        },
        "previous_campaign_finalized": {
            "required": True,
            "passed": gates.previous_campaign_finalized,
        },
        "storage_cap_configured": {
            "required": True,
            "passed": gates.storage_cap_configured,
        },
        "minimum_free_disk_controller": {
            "required": "PASS",
            "passed": gates.minimum_free_disk_controller_pass,
            "status": "PASS" if gates.minimum_free_disk_controller_pass else "FAIL",
            "detail": free_report,
        },
    }
    blockers = [name for name, g in gate_results.items() if not g["passed"]]
    return {
        "schema": f"{SCHEMA}_capture_start_gates",
        "decision": decision,
        "live_capture_started": False,
        "live_capture_would_start": decision == "ALLOW_START",
        "enable_live_capture": gates.enable_live_capture,
        "all_hard_gates_passed": not blockers,
        "gate_results": gate_results,
        "blockers": blockers,
        "event_study_readiness_status": "NOT_READY",
        "event_study_real_execution": False,
        "new_strategy_generated_count": 0,
        "exchange_write_attempt_count": 0,
        "note": (
            "New bounded capture segment may begin ONLY when all hard gates PASS "
            "and enable_live_capture is set; default path is dry-run/controller scaffolding."
        ),
    }
