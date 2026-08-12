"""Storage budget controller — soft/hard limits without per-event tree scans."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StorageBudgetController:
    soft_limit_bytes: int
    hard_limit_bytes: int
    minimum_free_disk_bytes: int = 512 * 1024 * 1024
    current_compressed_partition_bytes: int = 0
    current_manifest_bytes: int = 0
    estimated_next_hour_bytes: float = 0.0
    estimated_next_day_bytes: float = 0.0
    mode: str = "NORMAL"
    stop_requested: bool = False

    def observe_write(self, *, compressed_delta: int = 0, manifest_delta: int = 0) -> str:
        self.current_compressed_partition_bytes += max(0, compressed_delta)
        self.current_manifest_bytes += max(0, manifest_delta)
        total = self.current_compressed_partition_bytes + self.current_manifest_bytes
        if total >= self.hard_limit_bytes:
            self.mode = "STORAGE_BUDGET_BLOCKED"
            self.stop_requested = True
            return self.mode
        if total >= self.soft_limit_bytes:
            self.mode = "DEGRADED_STORAGE_MODE"
            return self.mode
        self.mode = "NORMAL"
        return self.mode

    def update_estimates(self, *, bytes_per_second: float) -> None:
        self.estimated_next_hour_bytes = bytes_per_second * 3600
        self.estimated_next_day_bytes = bytes_per_second * 86400

    def report(self) -> dict[str, Any]:
        return {
            "soft_limit_bytes": self.soft_limit_bytes,
            "hard_limit_bytes": self.hard_limit_bytes,
            "minimum_free_disk_bytes": self.minimum_free_disk_bytes,
            "current_compressed_partition_bytes": self.current_compressed_partition_bytes,
            "current_manifest_bytes": self.current_manifest_bytes,
            "estimated_next_hour_bytes": self.estimated_next_hour_bytes,
            "estimated_next_day_bytes": self.estimated_next_day_bytes,
            "mode": self.mode,
            "stop_requested": self.stop_requested,
            "storage_tree_scanned_per_event": False,
        }
