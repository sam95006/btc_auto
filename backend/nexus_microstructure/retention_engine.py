"""Retention / compaction engine — dry-run by default; never deletes in this task."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.derived_bars import build_trade_bars


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def retention_dry_run(root: Path, *, code_checksum: str) -> dict[str, Any]:
    partitions = list(root.rglob("*.jsonl.gz")) if root.exists() else []
    candidates = []
    total_bytes = 0
    for p in partitions:
        size = p.stat().st_size
        total_bytes += size
        age_hint = "UNKNOWN"
        candidates.append(
            {
                "path": str(p),
                "bytes": size,
                "proposed_tier": "RAW_HOT",
                "age_status": age_hint,
                "delete_allowed": False,
            }
        )
    # Compaction candidates: trade partitions only
    trade_parts = [c for c in candidates if "AGGRESSIVE_TRADE_FLOW" in c["path"]]
    compaction = []
    for c in trade_parts[:5]:
        compaction.append(
            {
                "source_partition": c["path"],
                "targets": ["1s", "5s", "1m"],
                "status": "DRY_RUN_ONLY",
                "compaction_code_checksum": code_checksum,
            }
        )
    return {
        "schema": "retention_dry_run",
        "dry_run": True,
        "deletion_executed": False,
        "retention_candidate_partition_count": len(candidates),
        "retention_candidate_bytes": total_bytes,
        "compaction_candidate_count": len(compaction),
        "compaction_output_checksum_status": "NOT_EXECUTED_DRY_RUN",
        "tiers_supported": ["RAW_HOT", "AGGREGATED_WARM", "LONG_TERM_RESEARCH"],
        "independent_retention_dimensions": [
            "exchange",
            "data_family",
            "symbol_class",
            "partition_age",
            "integrity_status",
        ],
        "compaction_plan_sample": compaction,
        "created_at": _utc(),
    }


def compaction_code_checksum() -> str:
    src = Path(__file__).read_bytes()
    return hashlib.sha256(src).hexdigest()
