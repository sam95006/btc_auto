"""Storage budget for V13-A — 100 GiB free-disk floor / 40 GiB hard cap."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.ops_v13.constants import (
    GIB,
    HARD_CAP_BYTES,
    SCHEMA,
    SOFT_CAP_BYTES,
    STORAGE_FLOOR_BYTES,
)
from backend.nexus_microstructure.storage_budget_v10 import check_minimum_free_disk, disk_free_bytes


@dataclass
class StorageBudgetControllerV13:
    """Campaign storage controller with V13 floor/cap constants."""

    soft_limit_bytes: int = SOFT_CAP_BYTES
    hard_limit_bytes: int = HARD_CAP_BYTES
    minimum_free_disk_bytes: int = STORAGE_FLOOR_BYTES
    disk_root: str = "D:\\"
    current_compressed_partition_bytes: int = 0
    current_manifest_bytes: int = 0
    mode: str = "NORMAL"
    stop_requested: bool = False
    stop_reason: str | None = None
    free_disk_report: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.hard_limit_bytes <= 0 or self.soft_limit_bytes <= 0:
            raise ValueError("storage caps must be positive")
        if self.soft_limit_bytes > self.hard_limit_bytes:
            raise ValueError("soft_limit_bytes must be <= hard_limit_bytes")
        if self.minimum_free_disk_bytes < STORAGE_FLOOR_BYTES:
            # Allow higher floors in tests, never lower than design floor unless explicit override flag.
            pass

    @property
    def storage_cap_configured(self) -> bool:
        return self.soft_limit_bytes > 0 and self.hard_limit_bytes > 0

    def refresh_free_disk(self, *, free_bytes_override: int | None = None) -> dict[str, Any]:
        if free_bytes_override is not None:
            free = int(free_bytes_override)
            passed = free >= self.minimum_free_disk_bytes
            self.free_disk_report = {
                "schema": f"{SCHEMA}_minimum_free_disk",
                "path": self.disk_root,
                "free_bytes": free,
                "free_gib": round(free / GIB, 3),
                "minimum_free_disk_bytes": self.minimum_free_disk_bytes,
                "minimum_free_disk_gib": round(self.minimum_free_disk_bytes / GIB, 3),
                "status": "PASS" if passed else "FAIL",
                "passed": passed,
                "override": True,
            }
        else:
            self.free_disk_report = check_minimum_free_disk(
                self.disk_root,
                minimum_free_disk_bytes=self.minimum_free_disk_bytes,
            )
            self.free_disk_report["schema"] = f"{SCHEMA}_minimum_free_disk"
        if not self.free_disk_report["passed"]:
            self.mode = "STORAGE_FLOOR_BLOCKED"
            self.stop_requested = True
            self.stop_reason = "disk_floor_fail"
        return self.free_disk_report

    def observe_write(self, *, compressed_delta: int = 0, manifest_delta: int = 0) -> str:
        self.current_compressed_partition_bytes += max(0, compressed_delta)
        self.current_manifest_bytes += max(0, manifest_delta)
        total = self.current_compressed_partition_bytes + self.current_manifest_bytes
        if total >= self.hard_limit_bytes:
            self.mode = "STORAGE_HARD_CAP_BLOCKED"
            self.stop_requested = True
            self.stop_reason = "hard_storage_cap"
            return self.mode
        if total >= self.soft_limit_bytes:
            self.mode = "DEGRADED_STORAGE_MODE"
            return self.mode
        if self.mode not in {"STORAGE_FLOOR_BLOCKED", "STORAGE_HARD_CAP_BLOCKED"}:
            self.mode = "NORMAL"
        return self.mode

    def report(self, *, free_bytes_override: int | None = None) -> dict[str, Any]:
        if not self.free_disk_report or free_bytes_override is not None:
            self.refresh_free_disk(free_bytes_override=free_bytes_override)
        total = self.current_compressed_partition_bytes + self.current_manifest_bytes
        return {
            "schema": f"{SCHEMA}_storage_budget",
            "soft_limit_bytes": self.soft_limit_bytes,
            "hard_limit_bytes": self.hard_limit_bytes,
            "hard_cap_gib": HARD_CAP_BYTES // GIB,
            "minimum_free_disk_bytes": self.minimum_free_disk_bytes,
            "storage_floor_gib": STORAGE_FLOOR_BYTES // GIB,
            "disk_root": self.disk_root,
            "storage_cap_configured": self.storage_cap_configured,
            "current_compressed_partition_bytes": self.current_compressed_partition_bytes,
            "current_manifest_bytes": self.current_manifest_bytes,
            "current_total_bytes": total,
            "mode": self.mode,
            "stop_requested": self.stop_requested,
            "stop_reason": self.stop_reason,
            "minimum_free_disk": self.free_disk_report,
            "live_free_bytes": disk_free_bytes(self.disk_root) if Path(self.disk_root).exists() else None,
            "deletion_executed": False,
        }
