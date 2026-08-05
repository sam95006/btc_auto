"""Storage migration/export guard — refuse in-flight open partitions (R2-D-005)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.collector_cutover_v2.constants import SCHEMA


class OpenPartitionMigrationBlocked(Exception):
    """Raised when a migration/export tree contains in-flight *.open markers."""

    def __init__(self, open_markers: list[str]) -> None:
        self.open_markers = list(open_markers)
        super().__init__(
            f"OPEN_PARTITION_MIGRATION_BLOCKED: count={len(open_markers)}"
        )


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_open_markers(root: Path) -> list[Path]:
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.jsonl.gz.open"))


def assert_migration_safe(root: Path) -> dict[str, Any]:
    """Hard gate: refuse copy/export/migrate when any partition is still open."""
    markers = find_open_markers(root)
    report = {
        "schema": f"{SCHEMA}_migration_safety",
        "root": str(root),
        "open_marker_count": len(markers),
        "open_markers": [str(p) for p in markers[:50]],
        "migration_allowed": len(markers) == 0,
        "created_at": _utc(),
        "r2_finding": "R2-D-005",
        "disposition": "FIXED",
    }
    if markers:
        raise OpenPartitionMigrationBlocked([str(p) for p in markers])
    return report


def migration_dry_run(root: Path) -> dict[str, Any]:
    """Evaluate without raising — used by storage controller reports."""
    markers = find_open_markers(root)
    return {
        "schema": f"{SCHEMA}_migration_dry_run",
        "root": str(root),
        "open_marker_count": len(markers),
        "open_markers": [str(p) for p in markers[:50]],
        "migration_allowed": len(markers) == 0,
        "would_block": len(markers) > 0,
        "created_at": _utc(),
        "r2_finding": "R2-D-005",
        "disposition": "FIXED",
        "bytes_copied": 0,
        "raw_modified": False,
    }
