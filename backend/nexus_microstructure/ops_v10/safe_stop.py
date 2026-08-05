"""Automatic safe stop — halt new capture / request stop without exchange writes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_microstructure.ops_v10.constants import SCHEMA


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AutomaticSafeStop:
    """Evaluate conditions that require an automatic safe stop of capture ops."""

    STOP_REASONS = (
        "hard_storage_cap",
        "minimum_free_disk_fail",
        "integrity_fail",
        "storage_cap_not_configured",
        "previous_campaign_not_finalized",
        "operator_request",
        "gate_block",
    )

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def evaluate(
        self,
        *,
        budget_report: dict[str, Any] | None = None,
        integrity_score: dict[str, Any] | None = None,
        storage_cap_configured: bool = True,
        previous_campaign_finalized: bool = True,
        operator_stop: bool = False,
        gate_decision: str | None = None,
    ) -> dict[str, Any]:
        budget = budget_report or {}
        integrity = integrity_score or {}
        reasons: list[str] = []

        if budget.get("stop_requested") or budget.get("mode") == "STORAGE_BUDGET_BLOCKED":
            reasons.append(budget.get("stop_reason") or "hard_storage_cap")
        min_disk = budget.get("minimum_free_disk") or {}
        if min_disk and not min_disk.get("passed", True):
            reasons.append("minimum_free_disk_fail")
        if integrity.get("integrity_overall") == "FAIL" or integrity.get("integrity_status") == "FAIL":
            reasons.append("integrity_fail")
        if not storage_cap_configured:
            reasons.append("storage_cap_not_configured")
        if not previous_campaign_finalized:
            reasons.append("previous_campaign_not_finalized")
        if operator_stop:
            reasons.append("operator_request")
        if gate_decision == "BLOCK_START":
            reasons.append("gate_block")

        # Deduplicate while preserving order
        reasons = list(dict.fromkeys(reasons))
        stop = bool(reasons)
        event = {
            "schema": f"{SCHEMA}_automatic_safe_stop",
            "safe_stop_required": stop,
            "safe_stop_executed": False,  # controller records intent; runner executes no live stop IPC
            "reasons": reasons,
            "primary_reason": reasons[0] if reasons else None,
            "exchange_write_attempt_count": 0,
            "live_capture_started": False,
            "event_study_real_execution": False,
            "created_at": _utc(),
        }
        self.events.append(event)
        return event

    def policy(self) -> dict[str, Any]:
        return {
            "schema": f"{SCHEMA}_safe_stop_policy",
            "stop_reasons_recognized": list(self.STOP_REASONS),
            "actions_on_stop": [
                "block_new_capture_segment",
                "request_collector_stop_if_running",
                "persist_checkpoint",
                "retain_partitions",
            ],
            "forbidden_actions": [
                "exchange_write",
                "event_study_start",
                "strategy_generation",
                "partition_deletion",
            ],
            "events": list(self.events),
        }
