"""Retention dry-run V10 — plan only; never deletes."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.ops_v10.constants import SCHEMA


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def retention_dry_run_v10(
    root: Path,
    *,
    code_checksum: str | None = None,
) -> dict[str, Any]:
    """Enumerate retention/compaction candidates without deleting anything."""
    root = Path(root)
    partitions = list(root.rglob("*.jsonl.gz")) if root.exists() else []
    candidates: list[dict[str, Any]] = []
    total_bytes = 0
    for p in partitions:
        size = p.stat().st_size
        total_bytes += size
        candidates.append(
            {
                "path": str(p),
                "bytes": size,
                "proposed_tier": "RAW_HOT",
                "delete_allowed": False,
                "action": "RETAIN",
            }
        )
    checksum = code_checksum or hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    compaction = [
        {
            "source_partition": c["path"],
            "targets": ["1s", "5s", "1m"],
            "status": "DRY_RUN_ONLY",
            "compaction_code_checksum": checksum,
        }
        for c in candidates
        if "AGGRESSIVE_TRADE_FLOW" in c["path"]
    ][:5]
    return {
        "schema": f"{SCHEMA}_retention_dry_run",
        "dry_run": True,
        "deletion_executed": False,
        "root": str(root),
        "retention_candidate_partition_count": len(candidates),
        "retention_candidate_bytes": total_bytes,
        "compaction_candidate_count": len(compaction),
        "compaction_plan_sample": compaction,
        "tiers_supported": ["RAW_HOT", "AGGREGATED_WARM", "LONG_TERM_RESEARCH"],
        "independent_retention_dimensions": [
            "exchange",
            "data_family",
            "symbol_class",
            "partition_age",
            "integrity_status",
        ],
        "compaction_output_checksum_status": "NOT_EXECUTED_DRY_RUN",
        "created_at": _utc(),
    }
