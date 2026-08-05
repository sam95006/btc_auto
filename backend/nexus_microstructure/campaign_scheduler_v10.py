"""Campaign scheduler V10 — gate-aware segment planning; dry-run by default.

Does not start Event Study, generate strategies, or perform exchange writes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.ops_v10.constants import (
    DEFAULT_PREVIOUS_CAMPAIGN_ID,
    MIN_FREE_DISK_BYTES_FOR_NEW_SEGMENT,
    SCHEMA,
)
from backend.nexus_microstructure.ops_v10.finalizer_bridge import FinalizerIntegrationV10
from backend.nexus_microstructure.ops_v10.gates import evaluate_capture_start_gates
from backend.nexus_microstructure.ops_v10.registry import CampaignRegistryV10
from backend.nexus_microstructure.ops_v10.resume import BoundedResumeController
from backend.nexus_microstructure.ops_v10.retention import retention_dry_run_v10
from backend.nexus_microstructure.ops_v10.safe_stop import AutomaticSafeStop
from backend.nexus_microstructure.storage_budget_v10 import (
    DEFAULT_HARD_CAP_BYTES,
    DEFAULT_SOFT_CAP_BYTES,
    StorageBudgetControllerV10,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CampaignSchedulerV10:
    """Plan / gate the next microstructure campaign segment."""

    def __init__(
        self,
        repo_root: Path,
        *,
        registry_path: Path | None = None,
        disk_root: str = "D:\\",
        previous_campaign_id: str = DEFAULT_PREVIOUS_CAMPAIGN_ID,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.disk_root = disk_root
        self.previous_campaign_id = previous_campaign_id
        self.registry = CampaignRegistryV10(
            registry_path
            or (self.repo_root / ".nexus_runtime/microstructure/ops_v10/registry.json")
        )
        self.budget = StorageBudgetControllerV10(
            soft_limit_bytes=DEFAULT_SOFT_CAP_BYTES,
            hard_limit_bytes=DEFAULT_HARD_CAP_BYTES,
            minimum_free_disk_bytes=MIN_FREE_DISK_BYTES_FOR_NEW_SEGMENT,
            disk_root=disk_root,
        )
        self.safe_stop = AutomaticSafeStop()
        self.finalizer = FinalizerIntegrationV10(
            self.repo_root,
            campaign_id=previous_campaign_id,
        )

    def run_controller_cycle(
        self,
        *,
        proposed_campaign_id: str = "ms_accum_v10_bounded_next",
        enable_live_capture: bool = False,
        partitions_root: Path | None = None,
        free_disk_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute one ops controller cycle (dry-run unless explicitly allowed)."""
        finalizer_pkg = self.finalizer.import_into_registry(self.registry)
        budget_report = self.budget.report()
        if free_disk_override is not None:
            budget_report = {
                **budget_report,
                "minimum_free_disk": free_disk_override,
            }
            if not free_disk_override.get("passed", True):
                budget_report["mode"] = "STORAGE_BUDGET_BLOCKED"
                budget_report["stop_requested"] = True
                budget_report["stop_reason"] = "minimum_free_disk_fail"

        prev_finalized = bool(finalizer_pkg.get("previous_campaign_finalized")) or (
            self.registry.previous_campaign_finalized(self.previous_campaign_id)
        )
        integrity = finalizer_pkg.get("integrity_score") or {}

        gates = evaluate_capture_start_gates(
            disk_root=self.disk_root,
            minimum_free_disk_bytes=MIN_FREE_DISK_BYTES_FOR_NEW_SEGMENT,
            previous_campaign_finalized=prev_finalized,
            storage_cap_configured=self.budget.storage_cap_configured,
            enable_live_capture=enable_live_capture,
            free_disk_override=free_disk_override or budget_report.get("minimum_free_disk"),
        )

        # Prior-campaign integrity is scored for reporting; it does not by itself
        # block a new segment (hard gates are free disk / finalized / caps).
        stop = self.safe_stop.evaluate(
            budget_report=budget_report,
            integrity_score=None,
            storage_cap_configured=self.budget.storage_cap_configured,
            previous_campaign_finalized=prev_finalized,
            gate_decision=gates["decision"] if gates["decision"] == "BLOCK_START" else None,
        )

        if self.registry.get(proposed_campaign_id) is None:
            self.registry.register_campaign(proposed_campaign_id)

        resume = BoundedResumeController(campaign_id=self.previous_campaign_id)
        prev = self.registry.get(self.previous_campaign_id) or {}
        resume_meta = prev.get("resume_checkpoint") or (
            (finalizer_pkg.get("finalizer_status") or {}).get("campaign_resume_metadata") or {}
        )
        if resume_meta:
            resume.from_finalizer_resume_metadata(resume_meta)
        resume_decision = resume.allow_bounded_resume()

        part_root = partitions_root or (
            self.repo_root / ".nexus_runtime/microstructure/partitions"
        )
        retention = retention_dry_run_v10(part_root)

        live_started = False
        segment_plan: dict[str, Any] = {
            "proposed_campaign_id": proposed_campaign_id,
            "action": "NO_LIVE_CAPTURE",
            "reason": gates["decision"],
        }
        if gates["decision"] == "ALLOW_START" and not stop["safe_stop_required"]:
            # Explicit live path — still only mark planned; collector not invoked here.
            segment_plan = {
                "proposed_campaign_id": proposed_campaign_id,
                "action": "LIVE_CAPTURE_AUTHORIZED_NOT_STARTED",
                "reason": (
                    "All gates PASS and enable_live_capture=True, but this ops lane "
                    "does not invoke the collector; orchestration must call capture separately."
                ),
            }
            live_started = False
        elif gates["decision"] == "DRY_RUN_ONLY":
            segment_plan = {
                "proposed_campaign_id": proposed_campaign_id,
                "action": "DRY_RUN_CONTROLLER_ONLY",
                "reason": "hard_gates_pass_but_live_capture_disabled",
            }
        else:
            self.registry.mark_safe_stopped(proposed_campaign_id, stop.get("primary_reason") or "gate_block")
            segment_plan = {
                "proposed_campaign_id": proposed_campaign_id,
                "action": "BLOCKED",
                "reason": gates.get("blockers") or stop.get("reasons"),
            }

        return {
            "schema": f"{SCHEMA}_scheduler_cycle",
            "created_at": _utc(),
            "previous_campaign_id": self.previous_campaign_id,
            "finalizer_integration": {
                "package_present": finalizer_pkg.get("package_present"),
                "previous_campaign_finalized": prev_finalized,
                "Microstructure_Finalizer_status": finalizer_pkg.get("Microstructure_Finalizer_status"),
                "event_study_readiness_status": "NOT_READY",
            },
            "storage_budget": budget_report,
            "capture_start_gates": gates,
            "automatic_safe_stop": stop,
            "bounded_resume": resume_decision,
            "retention_dry_run": retention,
            "integrity_score": integrity,
            "campaign_registry": self.registry.snapshot(),
            "segment_plan": segment_plan,
            "live_capture_started": live_started,
            "event_study_readiness_status": "NOT_READY",
            "event_study_real_execution": False,
            "new_strategy_generated_count": 0,
            "exchange_write_attempt_count": 0,
            "profitability_claim_count": 0,
        }
