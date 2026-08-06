"""Acceptance counters — founder zero-tolerance metrics."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_incremental_backfill_live_ingest.constants import (
    ACCEPTANCE_ZERO_COUNTERS,
    SCHEMA_COUNTERS,
)
from backend.nexus_incremental_backfill_live_ingest.hashing import utc_now_iso


@dataclass
class AcceptanceCounters:
    """Counters that must remain zero for PASS."""

    raw_rewrite_count: int = 0
    duplicate_unresolved_count: int = 0
    future_timestamp_accept_count: int = 0
    unlicensed_ingest_count: int = 0
    silent_gap_fill_count: int = 0
    # Informational (non-zero OK)
    ingested_count: int = 0
    duplicate_resolved_count: int = 0
    quarantined_count: int = 0
    rate_limit_pause_count: int = 0
    disk_quota_block_count: int = 0
    retention_prune_count: int = 0
    license_reject_count: int = 0
    partial_failure_recovered_count: int = 0
    live_append_count: int = 0
    backfill_batch_count: int = 0
    classification_counts: dict[str, int] = field(default_factory=dict)

    def bump_class(self, data_class: str) -> None:
        self.classification_counts[data_class] = int(self.classification_counts.get(data_class, 0)) + 1

    def acceptance_zeros_ok(self) -> bool:
        return all(int(getattr(self, name)) == 0 for name in ACCEPTANCE_ZERO_COUNTERS)

    def zero_snapshot(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in ACCEPTANCE_ZERO_COUNTERS}

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["schema"] = SCHEMA_COUNTERS
        d["updated_at"] = utc_now_iso()
        d["acceptance_zeros_ok"] = self.acceptance_zeros_ok()
        return d
