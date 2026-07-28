"""Worker health contracts for shadow pipeline workers."""
from __future__ import annotations

from typing import Any

from backend.nexus_global_shadow.contracts import WorkerHealth, now_ms

WORKER_TYPES = frozenset(
    {
        "universe",
        "market_data",
        "market_quality",
        "intelligence",
        "candidate",
        "six_role_review",
        "portfolio",
        "shadow_lifecycle",
        "reflection",
        "replay",
    }
)

HEALTH_STATES = frozenset({"HEALTHY", "DEGRADED", "STALLED", "FAILED", "DISABLED"})


class WorkerHealthRegistry:
    """Track worker health for all worker types."""

    def __init__(self) -> None:
        self._workers: dict[str, WorkerHealth] = {}

    def register(self, worker_id: str, worker_type: str, owner_id: str = "shadow") -> WorkerHealth:
        if worker_type not in WORKER_TYPES:
            worker_type = worker_type
        wh = WorkerHealth(
            worker_id=worker_id,
            worker_type=worker_type,
            owner_id=owner_id,
            health="DISABLED",
        )
        self._workers[worker_id] = wh
        return wh

    def heartbeat(
        self,
        worker_id: str,
        *,
        stage: str = "",
        health: str = "HEALTHY",
        queue_depth: int = 0,
        error: str | None = None,
    ) -> WorkerHealth | None:
        wh = self._workers.get(worker_id)
        if not wh:
            return None
        ts = now_ms()
        wh.last_progress_at = ts
        wh.current_stage = stage
        wh.health = health if health in HEALTH_STATES else "DEGRADED"
        wh.queue_depth = queue_depth
        if error:
            wh.last_error = error
            wh.consecutive_failures += 1
            wh.health = "FAILED" if wh.consecutive_failures >= 3 else "DEGRADED"
        else:
            wh.consecutive_failures = 0
        return wh

    def start(self, worker_id: str) -> WorkerHealth | None:
        wh = self._workers.get(worker_id)
        if wh:
            wh.last_started_at = now_ms()
            wh.health = "HEALTHY"
        return wh

    def complete(self, worker_id: str) -> WorkerHealth | None:
        wh = self._workers.get(worker_id)
        if wh:
            wh.last_completed_at = now_ms()
            wh.health = "HEALTHY"
        return wh

    def mark_stalled(self, worker_id: str, reason: str) -> WorkerHealth | None:
        wh = self._workers.get(worker_id)
        if wh:
            wh.stalled = True
            wh.stall_reason = reason
            wh.health = "STALLED"
        return wh

    def snapshot(self) -> list[dict[str, Any]]:
        return [w.to_dict() for w in self._workers.values()]

    def ensure_all_types_registered(self, owner_id: str = "shadow") -> None:
        for wt in WORKER_TYPES:
            wid = f"{wt}_worker"
            if wid not in self._workers:
                self.register(wid, wt, owner_id)
