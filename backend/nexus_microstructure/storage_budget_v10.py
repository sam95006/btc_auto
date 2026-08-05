"""Storage budget controller V10 — soft/hard caps + minimum free-disk gate.

Does not scan the full storage tree per event. Never deletes data.
Live capture start is gated elsewhere; this module only reports budget state.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GIB = 1024**3
# Founder V10 Lane D: new bounded segment requires D free space >= 30 GiB.
DEFAULT_MINIMUM_FREE_DISK_BYTES = 30 * GIB
DEFAULT_SOFT_CAP_BYTES = 805306368  # 768 MiB
DEFAULT_HARD_CAP_BYTES = 1073741824  # 1 GiB


def disk_free_bytes(path: str | Path) -> int:
    """Return free bytes on the volume that hosts ``path``."""
    usage = shutil.disk_usage(str(path))
    return int(usage.free)


def check_minimum_free_disk(
    path: str | Path,
    *,
    minimum_free_disk_bytes: int = DEFAULT_MINIMUM_FREE_DISK_BYTES,
) -> dict[str, Any]:
    """Evaluate the minimum free-disk controller (PASS / FAIL)."""
    free = disk_free_bytes(path)
    required = int(minimum_free_disk_bytes)
    passed = free >= required
    return {
        "schema": "minimum_free_disk_controller_v10",
        "path": str(path),
        "free_bytes": free,
        "free_gib": round(free / GIB, 3),
        "minimum_free_disk_bytes": required,
        "minimum_free_disk_gib": round(required / GIB, 3),
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
    }


@dataclass
class StorageBudgetControllerV10:
    """Bounded storage budget with automatic stop request on hard cap."""

    soft_limit_bytes: int = DEFAULT_SOFT_CAP_BYTES
    hard_limit_bytes: int = DEFAULT_HARD_CAP_BYTES
    minimum_free_disk_bytes: int = DEFAULT_MINIMUM_FREE_DISK_BYTES
    disk_root: str = "D:\\"
    current_compressed_partition_bytes: int = 0
    current_manifest_bytes: int = 0
    estimated_next_hour_bytes: float = 0.0
    estimated_next_day_bytes: float = 0.0
    mode: str = "NORMAL"
    stop_requested: bool = False
    stop_reason: str | None = None
    free_disk_report: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.hard_limit_bytes <= 0 or self.soft_limit_bytes <= 0:
            raise ValueError("storage caps must be configured to positive byte limits")
        if self.soft_limit_bytes > self.hard_limit_bytes:
            raise ValueError("soft_limit_bytes must be <= hard_limit_bytes")

    @property
    def storage_cap_configured(self) -> bool:
        return self.soft_limit_bytes > 0 and self.hard_limit_bytes > 0

    def refresh_free_disk(self) -> dict[str, Any]:
        self.free_disk_report = check_minimum_free_disk(
            self.disk_root,
            minimum_free_disk_bytes=self.minimum_free_disk_bytes,
        )
        if not self.free_disk_report["passed"]:
            self.mode = "STORAGE_BUDGET_BLOCKED"
            self.stop_requested = True
            self.stop_reason = "minimum_free_disk_fail"
        return self.free_disk_report

    def observe_write(self, *, compressed_delta: int = 0, manifest_delta: int = 0) -> str:
        self.current_compressed_partition_bytes += max(0, compressed_delta)
        self.current_manifest_bytes += max(0, manifest_delta)
        total = self.current_compressed_partition_bytes + self.current_manifest_bytes
        if total >= self.hard_limit_bytes:
            self.mode = "STORAGE_BUDGET_BLOCKED"
            self.stop_requested = True
            self.stop_reason = "hard_storage_cap"
            return self.mode
        if total >= self.soft_limit_bytes:
            self.mode = "DEGRADED_STORAGE_MODE"
            return self.mode
        if self.mode != "STORAGE_BUDGET_BLOCKED":
            self.mode = "NORMAL"
        return self.mode

    def update_estimates(self, *, bytes_per_second: float) -> None:
        self.estimated_next_hour_bytes = max(0.0, bytes_per_second) * 3600
        self.estimated_next_day_bytes = max(0.0, bytes_per_second) * 86400

    def report(self) -> dict[str, Any]:
        if not self.free_disk_report:
            self.refresh_free_disk()
        total = self.current_compressed_partition_bytes + self.current_manifest_bytes
        return {
            "schema": "storage_budget_controller_v10",
            "soft_limit_bytes": self.soft_limit_bytes,
            "hard_limit_bytes": self.hard_limit_bytes,
            "minimum_free_disk_bytes": self.minimum_free_disk_bytes,
            "disk_root": self.disk_root,
            "storage_cap_configured": self.storage_cap_configured,
            "current_compressed_partition_bytes": self.current_compressed_partition_bytes,
            "current_manifest_bytes": self.current_manifest_bytes,
            "current_total_bytes": total,
            "estimated_next_hour_bytes": self.estimated_next_hour_bytes,
            "estimated_next_day_bytes": self.estimated_next_day_bytes,
            "mode": self.mode,
            "stop_requested": self.stop_requested,
            "stop_reason": self.stop_reason,
            "minimum_free_disk": self.free_disk_report,
            "storage_tree_scanned_per_event": False,
            "deletion_executed": False,
        }
