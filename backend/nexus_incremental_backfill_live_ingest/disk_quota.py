"""Disk quota enforcement for bounded ingest."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_incremental_backfill_live_ingest.constants import DEFAULT_MAX_DISK_BYTES


class DiskQuotaExceeded(RuntimeError):
    pass


class DiskQuota:
    def __init__(self, root: Path, *, max_bytes: int = DEFAULT_MAX_DISK_BYTES) -> None:
        self.root = Path(root)
        self.max_bytes = int(max_bytes)

    def usage_bytes(self) -> int:
        if not self.root.exists():
            return 0
        total = 0
        for p in self.root.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
        return total

    def assert_can_write(self, incoming_bytes: int) -> None:
        if self.usage_bytes() + int(incoming_bytes) > self.max_bytes:
            raise DiskQuotaExceeded(
                f"disk_quota_exceeded:usage={self.usage_bytes()}:max={self.max_bytes}"
            )
