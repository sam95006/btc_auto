"""Storage metric truth: separate compressed vs uncompressed bytes."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any


def audit_partition_file(path: Path) -> dict[str, Any]:
    compressed = path.stat().st_size if path.is_file() else 0
    uncompressed = 0
    events = 0
    if path.is_file() and path.suffix == ".gz":
        with gzip.open(path, "rb") as fh:
            while True:
                chunk = fh.read(1024 * 256)
                if not chunk:
                    break
                uncompressed += len(chunk)
                events += chunk.count(b"\n")
    manifest = path.with_suffix(".manifest.json")
    if not manifest.exists() and path.name.endswith(".jsonl.gz"):
        manifest = Path(str(path)[: -len(".jsonl.gz")] + ".jsonl.manifest.json")
        # also try stem.manifest.json pattern used by V1.1
        alt = path.with_name(path.name.replace(".jsonl.gz", ".manifest.json"))
        if alt.exists():
            manifest = alt
    manifest_bytes = manifest.stat().st_size if manifest.is_file() else 0
    return {
        "path": str(path),
        "partition_compressed_bytes": compressed,
        "partition_uncompressed_bytes": uncompressed,
        "manifest_bytes": manifest_bytes,
        "event_count": events,
        "compression_ratio": (compressed / uncompressed) if uncompressed else None,
    }


def audit_storage_tree(root: Path) -> dict[str, Any]:
    parts = []
    for p in root.rglob("*.jsonl.gz"):
        parts.append(audit_partition_file(p))
    total_c = sum(x["partition_compressed_bytes"] for x in parts)
    total_u = sum(x["partition_uncompressed_bytes"] for x in parts)
    total_m = sum(x["manifest_bytes"] for x in parts)
    events = sum(x["event_count"] for x in parts)
    return {
        "schema": "storage_metric_audit",
        "partition_count": len(parts),
        "session_total_compressed_bytes": total_c,
        "session_total_uncompressed_bytes": total_u,
        "manifest_bytes": total_m,
        "filesystem_bytes_on_disk": total_c + total_m,
        "event_count": events,
        "actual_compressed_bytes_per_event": (total_c / events) if events else None,
        "actual_uncompressed_bytes_per_event": (total_u / events) if events else None,
        "actual_compression_ratio": (total_c / total_u) if total_u else None,
        "partitions_sample": parts[:20],
    }


def compare_to_v11_estimate(
    *,
    claimed_daily: float | None,
    actual_compressed_bpe: float | None,
    events_per_second: float | None,
    symbol_count: int,
) -> dict[str, Any]:
    if not actual_compressed_bpe or not events_per_second:
        return {"storage_metric_status": "STORAGE_ESTIMATE_INVALID", "reason": "missing_inputs"}
    actual_daily = actual_compressed_bpe * events_per_second * 86400
    # scale note: events_per_second already for the run's symbol set
    status = "STORAGE_ESTIMATE_CONFIRMED"
    if claimed_daily and claimed_daily > 0:
        ratio = claimed_daily / actual_daily if actual_daily else None
        if ratio and ratio > 1.25:
            status = "STORAGE_ESTIMATE_OVERSTATED"
        elif ratio and ratio < 0.75:
            status = "STORAGE_ESTIMATE_UNDERSTATED"
    return {
        "storage_metric_status": status,
        "claimed_daily_estimate": claimed_daily,
        "actual_daily_compressed_storage_estimate": actual_daily,
        "actual_30_day_compressed_storage_estimate": actual_daily * 30,
        "actual_365_day_compressed_storage_estimate": actual_daily * 365,
        "symbol_count_basis": symbol_count,
        "events_per_second_basis": events_per_second,
        "actual_compressed_bytes_per_event": actual_compressed_bpe,
    }
