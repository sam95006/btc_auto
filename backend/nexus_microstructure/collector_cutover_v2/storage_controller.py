"""Storage controller V2 — budget + migration gate + automatic safe stop."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.collector_cutover_v2.constants import SCHEMA
from backend.nexus_microstructure.collector_cutover_v2.migration_guard import (
    migration_dry_run,
)
from backend.nexus_microstructure.ops_v10.safe_stop import AutomaticSafeStop
from backend.nexus_microstructure.storage_budget_v10 import (
    DEFAULT_HARD_CAP_BYTES,
    DEFAULT_SOFT_CAP_BYTES,
    StorageBudgetControllerV10,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StorageControllerV2:
    """Compose storage budget, open-partition migration gate, and safe-stop."""

    def __init__(
        self,
        *,
        partitions_root: Path,
        soft_limit_bytes: int = DEFAULT_SOFT_CAP_BYTES,
        hard_limit_bytes: int = DEFAULT_HARD_CAP_BYTES,
        disk_root: str = "D:\\",
    ) -> None:
        self.partitions_root = Path(partitions_root)
        self.budget = StorageBudgetControllerV10(
            soft_limit_bytes=soft_limit_bytes,
            hard_limit_bytes=hard_limit_bytes,
            disk_root=disk_root,
        )
        self.safe_stop = AutomaticSafeStop()

    def observe_write(self, *, compressed_delta: int = 0, manifest_delta: int = 0) -> str:
        return self.budget.observe_write(
            compressed_delta=compressed_delta,
            manifest_delta=manifest_delta,
        )

    def evaluate(
        self,
        *,
        previous_campaign_finalized: bool = True,
        integrity_score: dict[str, Any] | None = None,
        operator_stop: bool = False,
        gate_decision: str | None = None,
    ) -> dict[str, Any]:
        budget_report = self.budget.report()
        migration = migration_dry_run(self.partitions_root)
        stop = self.safe_stop.evaluate(
            budget_report=budget_report,
            integrity_score=integrity_score,
            storage_cap_configured=self.budget.storage_cap_configured,
            previous_campaign_finalized=previous_campaign_finalized,
            operator_stop=operator_stop,
            gate_decision=gate_decision,
        )
        # Open partitions in the active tree block migration but do not by themselves
        # force capture stop (writer may still be sealing). Export tools must call assert.
        return {
            "schema": f"{SCHEMA}_storage_controller",
            "created_at": _utc(),
            "storage_budget": budget_report,
            "migration_safety": migration,
            "automatic_safe_stop": stop,
            "safe_stop_required": bool(stop.get("safe_stop_required")),
            "deletion_executed": False,
            "event_study_real_execution": False,
            "live_capture_started": False,
        }
