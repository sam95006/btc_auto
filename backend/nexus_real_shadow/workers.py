"""Worker health registry for Wave 5 real public shadow runtime."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow.contracts import WorkerHealth, now_ms

WAVE5_WORKER_TYPES = frozenset(
    {
        "instrument_discovery",
        "tier_scan",
        "market_data",
        "market_quality",
        "regime",
        "strategy",
        "candidate_rank",
        "six_role_review",
        "risk_veto",
        "mistake_guard",
        "portfolio",
        "adaptive_policy",
        "shadow_intent",
        "shadow_lifecycle",
        "reconciliation",
        "persistence",
    }
)


class Wave5WorkerHealthRegistry:
    """Track worker health; stalled workers block new entries."""

    def __init__(self) -> None:
        self._workers: dict[str, WorkerHealth] = {}

    def register(self, worker_id: str, worker_type: str, owner_id: str = "wave5") -> WorkerHealth:
        wh = WorkerHealth(
            worker_id=worker_id,
            worker_type=worker_type,
            owner_id=owner_id,
            health="DISABLED",
        )
        self._workers[worker_id] = wh
        return wh

    def ensure_all_types_registered(self, owner_id: str = "wave5") -> None:
        for wt in WAVE5_WORKER_TYPES:
            wid = f"{wt}_worker"
            if wid not in self._workers:
                self.register(wid, wt, owner_id)

    def heartbeat(self, worker_id: str, *, stage: str = "", health: str = "HEALTHY") -> WorkerHealth | None:
        wh = self._workers.get(worker_id)
        if not wh:
            return None
        wh.last_progress_at = now_ms()
        wh.current_stage = stage
        wh.health = health
        wh.stalled = False
        wh.stall_reason = None
        return wh

    def mark_stalled(self, worker_id: str, reason: str) -> WorkerHealth | None:
        wh = self._workers.get(worker_id)
        if wh:
            wh.stalled = True
            wh.stall_reason = reason
            wh.health = "STALLED"
        return wh

    def any_stalled(self) -> bool:
        return any(w.stalled for w in self._workers.values())

    def block_new_entries(self) -> bool:
        return self.any_stalled()

    def snapshot(self) -> list[dict[str, Any]]:
        return [w.to_dict() for w in self._workers.values()]
