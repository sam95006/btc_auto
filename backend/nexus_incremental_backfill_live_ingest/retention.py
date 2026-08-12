"""Retention policy — prune stale partition index entries, never rewrite raw."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.nexus_incremental_backfill_live_ingest.constants import DEFAULT_RETENTION_DAYS
from backend.nexus_incremental_backfill_live_ingest.hashing import utc_now_iso


class RetentionPolicy:
    """Drop expired date-partition *index* entries only — raw bronze stays append-only."""

    def __init__(self, *, retention_days: int = DEFAULT_RETENTION_DAYS) -> None:
        self.retention_days = int(retention_days)

    def cutoff_day(self, *, now: datetime | None = None) -> str:
        ref = now or datetime.now(timezone.utc)
        cut = ref - timedelta(days=self.retention_days)
        return cut.strftime("%Y-%m-%d")

    def prune_partition_index(self, partitions: dict[str, list[str]]) -> dict[str, Any]:
        """Remove partition keys older than retention from an in-memory index.

        Does NOT delete or rewrite bronze raw payloads (raw_rewrite_count stays 0).
        """
        cutoff = self.cutoff_day()
        kept: dict[str, list[str]] = {}
        pruned_keys: list[str] = []
        for day, hashes in partitions.items():
            if day < cutoff:
                pruned_keys.append(day)
            else:
                kept[day] = list(hashes)
        return {
            "cutoff_day": cutoff,
            "pruned_partition_count": len(pruned_keys),
            "pruned_partitions": pruned_keys,
            "kept": kept,
            "raw_rewritten": False,
            "pruned_at": utc_now_iso(),
        }
