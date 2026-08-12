"""Bounded memory/disk profiling smoke — document limits; no fake 15y claims."""
from __future__ import annotations

import sys
import tempfile
import tracemalloc
import os
from pathlib import Path
from typing import Any

from backend.nexus_deep_ingest_contamination.archive_recovery import CorruptArchiveRecovery
from backend.nexus_deep_ingest_contamination.constants import (
    BOUNDED_MAX_ARCHIVE_ENTRIES,
    BOUNDED_MAX_DISK_BYTES,
    BOUNDED_MAX_MEMORY_BYTES,
)
from backend.nexus_deep_ingest_contamination.duplicate_ingest import DuplicateDatasetIngestor
from backend.nexus_deep_ingest_contamination.hard_bans import (
    HardBanViolation,
    refuse_15y_history_claim,
)


def _rss_bytes() -> int | None:
    """Best-effort RSS. ``resource`` is unavailable on Windows — return None there."""
    try:
        import resource  # type: ignore
    except ImportError:
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        val = int(usage.ru_maxrss)
        if sys.platform.startswith("linux"):
            return val * 1024
        return val
    except Exception:
        return None


def run_bounded_resource_smoke(*, entry_count: int = 8) -> dict[str, Any]:
    """Allocate a bounded fixture archive + ingest set; assert documented ceilings."""
    # Explicitly document that we do NOT claim 15y history.
    try:
        refuse_15y_history_claim(claimed=True)
        ban_ok = False
    except HardBanViolation:
        ban_ok = True

    tracemalloc.start()
    peak_before = tracemalloc.get_traced_memory()[1]
    disk_used = 0
    current = 0
    peak = 0

    with tempfile.TemporaryDirectory(prefix="v17_deep_resource_") as tmp:
        root = Path(tmp) / "archive"
        archive = CorruptArchiveRecovery(
            root,
            max_disk_bytes=BOUNDED_MAX_DISK_BYTES,
            max_entries=BOUNDED_MAX_ARCHIVE_ENTRIES,
        )
        for i in range(entry_count):
            archive.pack_entry(
                f"entry_{i:03d}",
                {"i": i, "fixture": True, "blob": "x" * 64},
            )
        disk_used = archive.disk_usage_bytes()
        disk_ok = disk_used <= BOUNDED_MAX_DISK_BYTES

        budget_enforced = False
        tiny = CorruptArchiveRecovery(
            Path(tmp) / "tiny",
            max_disk_bytes=256,
            max_entries=BOUNDED_MAX_ARCHIVE_ENTRIES,
        )
        try:
            # Incompressible payload so zlib cannot shrink under the tiny disk ceiling.
            tiny.pack_entry("big", {"blob": os.urandom(4096).hex()})
        except HardBanViolation:
            budget_enforced = True

        ingestor = DuplicateDatasetIngestor(max_batches=BOUNDED_MAX_ARCHIVE_ENTRIES)
        for i in range(entry_count):
            ingestor.ingest(
                dataset_id=f"ds_{i}",
                payload={"i": i, "rows": list(range(16))},
                ingest_id=f"ing_{i}",
            )

        current, peak = tracemalloc.get_traced_memory()
        peak_delta = max(0, peak - peak_before)
        memory_ok = peak_delta <= BOUNDED_MAX_MEMORY_BYTES or peak <= BOUNDED_MAX_MEMORY_BYTES

    tracemalloc.stop()
    rss = _rss_bytes()

    return {
        "schema": "v17_deep_bounded_resource_smoke_v1",
        "status": "PASS" if disk_ok and budget_enforced and ban_ok and memory_ok else "FAIL",
        "limits": {
            "max_disk_bytes": BOUNDED_MAX_DISK_BYTES,
            "max_memory_bytes": BOUNDED_MAX_MEMORY_BYTES,
            "max_archive_entries": BOUNDED_MAX_ARCHIVE_ENTRIES,
        },
        "observed": {
            "disk_used_bytes": disk_used,
            "tracemalloc_current_bytes": current,
            "tracemalloc_peak_bytes": peak,
            "tracemalloc_peak_delta_bytes": peak_delta,
            "rss_bytes": rss,
            "entry_count": entry_count,
            "rss_available": rss is not None,
        },
        "disk_within_budget": disk_ok,
        "disk_budget_enforced": budget_enforced,
        "memory_within_documented_ceiling": memory_ok,
        "claims_15y_history_downloaded": False,
        "fifteen_year_claim_banned": ban_ok,
        "fixture_only": True,
        "note": (
            "Bounded smoke only — documents fixture-round ceilings; "
            "NOT a production capacity or 15y history proof."
        ),
    }


def resource_limits_document() -> dict[str, Any]:
    return {
        "BOUNDED_MAX_DISK_BYTES": BOUNDED_MAX_DISK_BYTES,
        "BOUNDED_MAX_MEMORY_BYTES": BOUNDED_MAX_MEMORY_BYTES,
        "BOUNDED_MAX_ARCHIVE_ENTRIES": BOUNDED_MAX_ARCHIVE_ENTRIES,
        "claims_15y_history_downloaded": False,
        "full_history_ingest_this_round": False,
    }
