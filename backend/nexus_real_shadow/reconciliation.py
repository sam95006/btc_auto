"""Restart reconciliation for real public shadow runtime."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ReconciliationStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class ReconciliationResult:
    status: ReconciliationStatus
    detail: str
    block_new_entries: bool
    persisted_open_count: int = 0
    runtime_open_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "detail": self.detail,
            "block_new_entries": self.block_new_entries,
            "persisted_open_count": self.persisted_open_count,
            "runtime_open_count": self.runtime_open_count,
        }


class ShadowReconciliationService:
    """Compare persisted shadow state with in-memory runtime on restart."""

    def reconcile(
        self,
        *,
        persisted_positions: list[dict[str, Any]] | None,
        runtime_positions: list[dict[str, Any]] | None,
    ) -> ReconciliationResult:
        persisted = [p for p in (persisted_positions or []) if p.get("state") == "SHADOW_OPEN"]
        runtime = [p for p in (runtime_positions or []) if p.get("state") == "SHADOW_OPEN"]
        p_count = len(persisted)
        r_count = len(runtime)

        if p_count == 0 and r_count == 0:
            return ReconciliationResult(
                status=ReconciliationStatus.MATCH,
                detail="empty_state_match",
                block_new_entries=False,
            )

        p_ids = {str(p.get("position_id")) for p in persisted if p.get("position_id")}
        r_ids = {str(p.get("position_id")) for p in runtime if p.get("position_id")}

        if p_ids == r_ids and p_count == r_count:
            return ReconciliationResult(
                status=ReconciliationStatus.MATCH,
                detail="position_ids_match",
                block_new_entries=False,
                persisted_open_count=p_count,
                runtime_open_count=r_count,
            )

        if not p_ids or not r_ids:
            return ReconciliationResult(
                status=ReconciliationStatus.AMBIGUOUS,
                detail="partial_state_on_restart",
                block_new_entries=True,
                persisted_open_count=p_count,
                runtime_open_count=r_count,
            )

        overlap = p_ids & r_ids
        if overlap and overlap != p_ids and overlap != r_ids:
            return ReconciliationResult(
                status=ReconciliationStatus.AMBIGUOUS,
                detail="partial_overlap",
                block_new_entries=True,
                persisted_open_count=p_count,
                runtime_open_count=r_count,
            )

        return ReconciliationResult(
            status=ReconciliationStatus.MISMATCH,
            detail="position_set_mismatch",
            block_new_entries=True,
            persisted_open_count=p_count,
            runtime_open_count=r_count,
        )


# Spec alias
ShadowRuntimeReconciler = ShadowReconciliationService
