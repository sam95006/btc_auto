"""V13-A controller — campaign design + synthetic preflight; never starts live capture."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.collector_cutover_v2.constants import (
    RETAINED_CLASSIFICATION_COUNTS as CUTOVER_RETAINED,
)
from backend.nexus_microstructure.collector_cutover_v2.open_tail_seal import open_tail_seal_policy
from backend.nexus_microstructure.event_study_hard_block_v11_1 import event_study_gate
from backend.nexus_microstructure.ops_v10.safe_stop import AutomaticSafeStop
from backend.nexus_microstructure.ops_v13.adversarial import run_adversarial_pass2
from backend.nexus_microstructure.ops_v13.campaign_design import build_campaign_design
from backend.nexus_microstructure.ops_v13.constants import (
    CAMPAIGN_ID,
    EVENT_STUDY_MUST_REMAIN,
    HARD_CAP_BYTES,
    LANE,
    PREVIOUS_CAMPAIGN_ID,
    RETAINED_CLASSIFICATION_COUNTS,
    SCHEMA,
    STORAGE_FLOOR_BYTES,
)
from backend.nexus_microstructure.ops_v13.gates import evaluate_capture_start_gates_v13
from backend.nexus_microstructure.ops_v13.storage_budget import StorageBudgetControllerV13
from backend.nexus_microstructure.ops_v13.synthetic_harness import run_all_preflight_scenarios


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MicrostructureOperationsControllerV13:
    """Orchestrate V13-A design + synthetic preflight evidence."""

    def __init__(
        self,
        repo_root: Path,
        *,
        work_root: Path,
        disk_root: str = "D:\\",
        previous_campaign_finalized: bool = True,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.work_root = Path(work_root)
        self.disk_root = disk_root
        self.previous_campaign_finalized = previous_campaign_finalized
        self.work_root.mkdir(parents=True, exist_ok=True)

    def run_pass1(self) -> dict[str, Any]:
        design = build_campaign_design()
        preflight = run_all_preflight_scenarios(self.work_root / "preflight")
        budget = StorageBudgetControllerV13(disk_root=self.disk_root)
        budget_report = budget.report()
        stop = AutomaticSafeStop().evaluate(
            budget_report=budget_report,
            storage_cap_configured=True,
            previous_campaign_finalized=self.previous_campaign_finalized,
        )
        gates = evaluate_capture_start_gates_v13(
            disk_root=self.disk_root,
            previous_campaign_finalized=self.previous_campaign_finalized,
            storage_cap_configured=True,
            preflight_synthetic_passed=bool(preflight.get("all_passed")),
            enable_live_capture=False,
            coordinator_authorized=False,
            free_disk_override=budget_report.get("minimum_free_disk"),
        )
        seal_pol = open_tail_seal_policy()
        gate = event_study_gate()

        retained_ok = (
            RETAINED_CLASSIFICATION_COUNTS["ACTUAL_DATA_CORRUPTION"] == 0
            and RETAINED_CLASSIFICATION_COUNTS["EXPECTED_OPEN_TAIL"] == 113
            and CUTOVER_RETAINED["ACTUAL_DATA_CORRUPTION"] == 0
            and seal_pol["prior_campaign_raw_modified"] is False
        )

        all_ok = (
            bool(preflight.get("all_passed"))
            and design["symbol_count"] >= 25
            and design["target_calendar_days"] == 14
            and design["storage"]["floor_free_disk_gib"] == 100
            and design["storage"]["hard_cap_gib"] == 40
            and retained_ok
            and gates["live_capture_started"] is False
            and gate.get("event_study") == EVENT_STUDY_MUST_REMAIN
        )

        return {
            "schema": f"{SCHEMA}_pass1",
            "lane": LANE,
            "created_at": _utc(),
            "campaign_id": CAMPAIGN_ID,
            "previous_campaign_id": PREVIOUS_CAMPAIGN_ID,
            "pass": 1,
            "all_passed": all_ok,
            "campaign_design": design,
            "preflight": preflight,
            "storage_budget": budget_report,
            "automatic_safe_stop": stop,
            "capture_start_gates": gates,
            "open_tail_seal_policy": seal_pol,
            "retained_classifications": {
                "raw_modified": False,
                "classification_counts": dict(RETAINED_CLASSIFICATION_COUNTS),
            },
            "event_study_gate": gate,
            "event_study_readiness_status": EVENT_STUDY_MUST_REMAIN,
            "event_study_real_execution": False,
            "live_capture_started": False,
            "exchange_write_attempt_count": 0,
            "demo_used": False,
            "mainnet_used": False,
            "shadow_used": False,
            "PR27_merged": False,
            "G_deleted": False,
            "raw_prior_campaign_modified": False,
            "storage_floor_bytes": STORAGE_FLOOR_BYTES,
            "hard_cap_bytes": HARD_CAP_BYTES,
        }

    def run_pass2(self) -> dict[str, Any]:
        return run_adversarial_pass2(self.work_root / "adversarial")

    def run_both_passes(self) -> dict[str, Any]:
        pass1 = self.run_pass1()
        pass2 = self.run_pass2()
        overall = bool(pass1.get("all_passed")) and bool(pass2.get("all_passed"))
        return {
            "schema": f"{SCHEMA}_both_passes",
            "created_at": _utc(),
            "lane": LANE,
            "campaign_id": CAMPAIGN_ID,
            "all_passed": overall,
            "pass1": pass1,
            "pass2": pass2,
            "live_capture_started": False,
            "event_study_readiness_status": EVENT_STUDY_MUST_REMAIN,
            "auto_integration": False,
        }
