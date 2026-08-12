"""Capture start gates for V13-A 14-day ops (Coordinator-gated live launch)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.nexus_microstructure.ops_v13.constants import (
    EVENT_STUDY_MUST_REMAIN,
    HARD_CAP_BYTES,
    SCHEMA,
    STORAGE_FLOOR_BYTES,
)
from backend.nexus_microstructure.storage_budget_v10 import check_minimum_free_disk


@dataclass
class CaptureStartGatesV13:
    disk_floor_ok: bool
    previous_campaign_finalized: bool
    storage_cap_configured: bool
    preflight_synthetic_passed: bool
    enable_live_capture: bool = False
    coordinator_authorized: bool = False

    def decision(self) -> str:
        all_pass = (
            self.disk_floor_ok
            and self.previous_campaign_finalized
            and self.storage_cap_configured
            and self.preflight_synthetic_passed
        )
        if not all_pass:
            return "BLOCK_START"
        # This lane never starts live capture; even with enable flags stay dry-run
        # unless Coordinator sets coordinator_authorized (still does not invoke collector here).
        if not self.enable_live_capture or not self.coordinator_authorized:
            return "DRY_RUN_ONLY"
        return "ALLOW_START_COORDINATOR_ONLY"


def evaluate_capture_start_gates_v13(
    *,
    disk_root: str = "D:\\",
    minimum_free_disk_bytes: int = STORAGE_FLOOR_BYTES,
    previous_campaign_finalized: bool,
    storage_cap_configured: bool = True,
    preflight_synthetic_passed: bool,
    enable_live_capture: bool = False,
    coordinator_authorized: bool = False,
    free_disk_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    free_report = free_disk_override or check_minimum_free_disk(
        disk_root,
        minimum_free_disk_bytes=minimum_free_disk_bytes,
    )
    gates = CaptureStartGatesV13(
        disk_floor_ok=bool(free_report.get("passed")),
        previous_campaign_finalized=bool(previous_campaign_finalized),
        storage_cap_configured=bool(storage_cap_configured) and HARD_CAP_BYTES > 0,
        preflight_synthetic_passed=bool(preflight_synthetic_passed),
        enable_live_capture=bool(enable_live_capture),
        coordinator_authorized=bool(coordinator_authorized),
    )
    decision = gates.decision()
    gate_results = {
        "disk_floor_ge_100_gib": {
            "required": True,
            "passed": gates.disk_floor_ok,
            "detail": free_report,
        },
        "previous_campaign_finalized": {
            "required": True,
            "passed": gates.previous_campaign_finalized,
        },
        "storage_hard_cap_40_gib_configured": {
            "required": True,
            "passed": gates.storage_cap_configured,
            "hard_cap_bytes": HARD_CAP_BYTES,
        },
        "preflight_synthetic_passed": {
            "required": True,
            "passed": gates.preflight_synthetic_passed,
        },
        "coordinator_authorized_for_live": {
            "required_for_live": True,
            "passed": gates.coordinator_authorized,
            "note": "This agent lane never sets this true.",
        },
    }
    blockers = [
        name
        for name, g in gate_results.items()
        if name != "coordinator_authorized_for_live" and not g["passed"]
    ]
    return {
        "schema": f"{SCHEMA}_capture_start_gates",
        "decision": decision,
        "live_capture_started": False,
        "live_capture_would_start": False,  # agent lane never starts
        "enable_live_capture": gates.enable_live_capture,
        "coordinator_authorized": gates.coordinator_authorized,
        "all_hard_gates_passed": not blockers,
        "gate_results": gate_results,
        "blockers": blockers,
        "event_study_readiness_status": EVENT_STUDY_MUST_REMAIN,
        "event_study_real_execution": False,
        "exchange_write_attempt_count": 0,
        "note": (
            "Live collector launch is Coordinator-only after synthetic preflight PASS. "
            "V13-A agent keeps live_capture_started=false."
        ),
    }
