"""Storage velocity and disk projection (read-only)."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.constants import (
    DISK_PROJECTION_HORIZON_HOURS,
    GIB,
    HARD_CAP_BYTES,
    SOFT_CAP_BYTES,
    STORAGE_FLOOR_BYTES,
    STORAGE_VELOCITY_SAMPLE_SECONDS,
)
from backend.nexus_capture_supervisor.util import finding, utc_stamp


def _tree_bytes(root: Path) -> tuple[int, int]:
    if not root.is_dir():
        return 0, 0
    total = 0
    count = 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
                count += 1
            except OSError:
                continue
    return total, count


def measure_storage_velocity(
    *,
    partitions_root: Path,
    sample_seconds: float = float(STORAGE_VELOCITY_SAMPLE_SECONDS),
    prior_bytes: int | None = None,
    prior_ts: float | None = None,
) -> dict[str, Any]:
    """Measure bytes/sec. If prior sample provided, avoid sleeping."""
    root = Path(partitions_root)
    t1 = time.time()
    b1, c1 = _tree_bytes(root)

    if prior_bytes is not None and prior_ts is not None and t1 > prior_ts:
        dt = t1 - prior_ts
        delta = b1 - int(prior_bytes)
        bps = delta / dt if dt > 0 else 0.0
        return {
            "method": "prior_delta",
            "bytes": b1,
            "file_count": c1,
            "delta_bytes": delta,
            "delta_seconds": dt,
            "bytes_per_second": bps,
            "sampled_at": utc_stamp(),
        }

    if sample_seconds <= 0:
        return {
            "method": "instant",
            "bytes": b1,
            "file_count": c1,
            "delta_bytes": 0,
            "delta_seconds": 0.0,
            "bytes_per_second": 0.0,
            "sampled_at": utc_stamp(),
        }

    time.sleep(float(sample_seconds))
    t2 = time.time()
    b2, c2 = _tree_bytes(root)
    dt = max(t2 - t1, 1e-6)
    delta = b2 - b1
    return {
        "method": "sleep_sample",
        "bytes": b2,
        "file_count": c2,
        "bytes_before": b1,
        "file_count_before": c1,
        "delta_bytes": delta,
        "delta_seconds": dt,
        "bytes_per_second": delta / dt,
        "sampled_at": utc_stamp(),
    }


def project_disk(
    *,
    disk_root: str,
    campaign_bytes: int,
    bytes_per_second: float,
    hard_cap_bytes: int = HARD_CAP_BYTES,
    soft_cap_bytes: int = SOFT_CAP_BYTES,
    floor_bytes: int = STORAGE_FLOOR_BYTES,
    horizon_hours: float = float(DISK_PROJECTION_HORIZON_HOURS),
) -> dict[str, Any]:
    usage = shutil.disk_usage(disk_root)
    free = int(usage.free)
    findings: list[dict[str, Any]] = []

    floor_ok = free >= floor_bytes
    under_hard = campaign_bytes < hard_cap_bytes
    under_soft = campaign_bytes < soft_cap_bytes

    if not floor_ok:
        findings.append(
            finding(
                code="DISK_FLOOR_BREACH",
                severity="CRITICAL",
                summary="Free disk below hard floor",
                evidence={"free_bytes": free, "floor_bytes": floor_bytes},
                recommendation="Coordinator: automatic safe stop required",
            )
        )
    if not under_hard:
        findings.append(
            finding(
                code="HARD_CAP_BREACH",
                severity="CRITICAL",
                summary="Campaign bytes exceed hard storage cap",
                evidence={"campaign_bytes": campaign_bytes, "hard_cap_bytes": hard_cap_bytes},
                recommendation="Coordinator: automatic safe stop required",
            )
        )
    elif not under_soft:
        findings.append(
            finding(
                code="SOFT_CAP_BREACH",
                severity="HIGH",
                summary="Campaign bytes exceed soft storage cap",
                evidence={"campaign_bytes": campaign_bytes, "soft_cap_bytes": soft_cap_bytes},
                recommendation="Coordinator: prepare graceful stop before hard cap",
            )
        )

    projected_bytes = campaign_bytes + max(0.0, bytes_per_second) * horizon_hours * 3600.0
    projected_free = free - max(0.0, bytes_per_second) * horizon_hours * 3600.0
    hours_to_hard = None
    hours_to_floor = None
    if bytes_per_second > 0:
        hours_to_hard = max(0.0, (hard_cap_bytes - campaign_bytes) / bytes_per_second) / 3600.0
        hours_to_floor = max(0.0, (free - floor_bytes) / bytes_per_second) / 3600.0
        if hours_to_hard is not None and hours_to_hard < horizon_hours:
            findings.append(
                finding(
                    code="HARD_CAP_PROJECTED",
                    severity="HIGH",
                    summary="Hard cap projected within horizon at current velocity",
                    evidence={"hours_to_hard_cap": hours_to_hard, "horizon_hours": horizon_hours},
                )
            )
        if hours_to_floor is not None and hours_to_floor < horizon_hours:
            findings.append(
                finding(
                    code="FLOOR_PROJECTED",
                    severity="HIGH",
                    summary="Disk floor projected within horizon at current velocity",
                    evidence={"hours_to_floor": hours_to_floor, "horizon_hours": horizon_hours},
                )
            )

    status = "OK"
    if any(f["severity"] == "CRITICAL" for f in findings):
        status = "STOP_REQUIRED"
    elif findings:
        status = "WARN"

    return {
        "schema": "v14_a_storage_projection",
        "observed_at": utc_stamp(),
        "disk_root": disk_root,
        "free_bytes": free,
        "free_gib": round(free / GIB, 2),
        "total_bytes": int(usage.total),
        "campaign_bytes": campaign_bytes,
        "campaign_gib": round(campaign_bytes / GIB, 4),
        "bytes_per_second": bytes_per_second,
        "bytes_per_hour": bytes_per_second * 3600.0,
        "projected_campaign_bytes_horizon": int(projected_bytes),
        "projected_free_bytes_horizon": int(projected_free),
        "hours_to_hard_cap": hours_to_hard,
        "hours_to_floor": hours_to_floor,
        "horizon_hours": horizon_hours,
        "floor_ok": floor_ok,
        "under_soft_cap": under_soft,
        "under_hard_cap": under_hard,
        "hard_cap_bytes": hard_cap_bytes,
        "soft_cap_bytes": soft_cap_bytes,
        "floor_bytes": floor_bytes,
        "status": status,
        "findings": findings,
    }
