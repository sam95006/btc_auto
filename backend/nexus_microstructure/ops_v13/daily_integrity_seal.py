"""Daily integrity seal for V13-A multi-day campaigns."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.integrity_recovery_v11.classify import discover_partitions_v11
from backend.nexus_microstructure.ops_v13.constants import CAMPAIGN_ID, SCHEMA


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_day_key(exchange_ts_ms: int) -> str:
    dt = datetime.fromtimestamp(exchange_ts_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y%m%d")


def seal_day(
    partitions_root: Path,
    *,
    campaign_id: str = CAMPAIGN_ID,
    day_key: str,
    seal_dir: Path | None = None,
) -> dict[str, Any]:
    """Compute and atomically persist a daily integrity seal over sealed partitions.

    Open-tail partitions are counted but do not block seal persistence; they are
    recorded so resume/ops can fence them. Does not mutate partition bytes.
    """
    partitions_root = Path(partitions_root)
    parts = discover_partitions_v11(partitions_root)
    day_parts: list[dict[str, Any]] = []
    for p in parts:
        hour = str(p.get("UTC_hour") or "")
        # UTC_hour format YYYYMMDD_HH
        if hour.startswith(day_key):
            day_parts.append(p)

    open_tails = [p for p in day_parts if p.get("is_open_tail") or p.get("open_marker_present")]
    sealed = [p for p in day_parts if p.get("manifest_present") and not p.get("is_open_tail")]
    checksum_ok = all(
        p.get("checksum_match") is not False for p in sealed if p.get("manifest_present")
    )

    material = {
        "campaign_id": campaign_id,
        "day_key": day_key,
        "partition_ids": sorted(str(p.get("partition_id")) for p in day_parts),
        "sealed_count": len(sealed),
        "open_tail_count": len(open_tails),
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    body = {
        "schema": f"{SCHEMA}_daily_integrity_seal",
        "campaign_id": campaign_id,
        "day_key": day_key,
        "created_at": _utc(),
        "partition_count": len(day_parts),
        "sealed_partition_count": len(sealed),
        "open_tail_count": len(open_tails),
        "checksum_replay_ok": checksum_ok,
        "seal_digest_sha256": digest,
        "partition_ids": material["partition_ids"],
        "integrity_status": "PASS" if checksum_ok and not open_tails else "HOLD_OPEN_TAILS_OR_MISMATCH",
        "raw_modified": False,
        "event_study_readiness_status": "NOT_READY",
    }

    out_dir = Path(seal_dir) if seal_dir else (partitions_root / "_daily_seals")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{campaign_id}_{day_key}.daily_seal.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    body["seal_path"] = str(path)
    body["atomic_write"] = True
    return body
