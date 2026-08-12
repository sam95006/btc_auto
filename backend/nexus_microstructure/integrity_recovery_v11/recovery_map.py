"""Hash-preserving recovery map — never rewrites raw campaign bytes."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.integrity_recovery_v11.constants import SCHEMA


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_recovery_map(
    partitions: list[dict[str, Any]],
    classifications: dict[str, Any],
    *,
    campaign_id: str,
    linkage_v11: dict[str, Any],
    linkage_legacy: dict[str, Any],
) -> dict[str, Any]:
    """Map each original file hash → classification / disposition (no silent repair)."""
    by_pid = {f["partition_id"]: f for f in classifications.get("findings") or []}
    entries: list[dict[str, Any]] = []
    for p in partitions:
        pid = p.get("partition_id")
        finding = by_pid.get(pid) or {}
        disposition = "KEEP_AS_IS"
        if p.get("is_open_tail"):
            disposition = "SEAL_AS_OPEN_TAIL_SIDECAR_ONLY"
        elif not p.get("manifest_present") and p.get("integrity_status") == "OK":
            disposition = "MANIFEST_REBUILD_ALLOWED_FROM_REPLAY_ONLY"
        elif p.get("checksum_match") is False:
            disposition = "QUARANTINE_NO_AUTO_REPAIR"

        entries.append(
            {
                "partition_id": pid,
                "path": p.get("path"),
                "original_sha256_file": p.get("original_sha256_file"),
                "rolling_checksum": p.get("rolling_checksum"),
                "replayed_checksum": p.get("replayed_checksum"),
                "partial_sha256": p.get("partial_sha256"),
                "integrity_status": p.get("integrity_status"),
                "is_open_tail": p.get("is_open_tail"),
                "manifest_present": p.get("manifest_present"),
                "primary_classification": finding.get("primary_classification"),
                "classifications": finding.get("classifications") or [],
                "disposition": disposition,
                "raw_bytes_modified": False,
            }
        )

    payload = {
        "schema": f"{SCHEMA}_recovery_map",
        "campaign_id": campaign_id,
        "created_at": _utc(),
        "raw_bytes_modified": False,
        "silent_repair_executed": False,
        "event_study_readiness_status": "NOT_READY",
        "event_study_real_execution": False,
        "partition_count": len(entries),
        "classification_counts": classifications.get("classification_counts"),
        "linkage_v1_breaks": linkage_legacy.get("linkage_breaks"),
        "linkage_v11_breaks": linkage_v11.get("linkage_breaks"),
        "linkage_false_positive_delta": int(linkage_legacy.get("linkage_breaks") or 0)
        - int(linkage_v11.get("linkage_breaks") or 0),
        "entries": entries,
        "map_sha256": None,
    }
    # Stable hash over entries' original hashes (order by partition_id)
    material = json.dumps(
        [{"partition_id": e["partition_id"], "original_sha256_file": e["original_sha256_file"]} for e in entries],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload["map_sha256"] = hashlib.sha256(material).hexdigest()
    payload["original_hashes_preserved"] = True
    return payload


def write_recovery_map(path: Path, recovery_map: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recovery_map, indent=2) + "\n", encoding="utf-8")
    return path
