"""Open-tail accounting (read-only; never mutates open tails)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.constants import OPEN_TAIL_STALE_SECONDS
from backend.nexus_capture_supervisor.partition_accounting import scan_partition_tree
from backend.nexus_capture_supervisor.util import finding, utc_hour_key, utc_now, utc_stamp


def account_open_tails(
    *,
    partitions_root: Path,
    campaign_id: str,
    stale_seconds: int = OPEN_TAIL_STALE_SECONDS,
) -> dict[str, Any]:
    scan = scan_partition_tree(partitions_root)
    findings: list[dict[str, Any]] = []
    if scan["status"] != "OK":
        findings.append(
            finding(
                code="OPEN_TAIL_SCAN_UNAVAILABLE",
                severity="CRITICAL",
                summary="Cannot account open tails — partitions root missing",
                evidence={"path": scan.get("path")},
            )
        )
        return {
            "schema": "v14_a_open_tail_accounting",
            "observed_at": utc_stamp(),
            "campaign_id": campaign_id,
            "status": "UNAVAILABLE",
            "findings": findings,
        }

    now = time.time()
    current_hour = utc_hour_key(utc_now())
    open_rows = [r for r in scan["partitions"] if r.get("is_open_tail")]
    expected_current = [r for r in open_rows if r.get("UTC_hour") == current_hour]
    stale = [
        r
        for r in open_rows
        if r.get("UTC_hour") != current_hour and (now - float(r.get("mtime") or 0)) > stale_seconds
    ]
    interrupted = [
        r for r in open_rows if r.get("open_marker_present") and not r.get("manifest_present")
    ]

    if stale:
        findings.append(
            finding(
                code="STALE_OPEN_TAILS",
                severity="HIGH",
                summary=f"{len(stale)} open-tail partitions outside current hour exceed stale threshold",
                evidence={
                    "stale_count": len(stale),
                    "stale_seconds": stale_seconds,
                    "examples": [s["path"] for s in stale[:8]],
                },
                recommendation="Retain open tails; fence on resume; do not rewrite or delete",
            )
        )

    # Many open tails in current hour is expected while LIVE_WRITING.
    status = "EXPECTED_OPEN_TAILS" if open_rows and not stale else ("CLEAN" if not open_rows else "STALE_PRESENT")
    if findings and any(f["severity"] in {"CRITICAL", "HIGH"} for f in findings):
        status = "FINDINGS"

    return {
        "schema": "v14_a_open_tail_accounting",
        "observed_at": utc_stamp(),
        "campaign_id": campaign_id,
        "status": status,
        "open_tail_count": len(open_rows),
        "expected_current_hour_open_tails": len(expected_current),
        "stale_open_tail_count": len(stale),
        "interrupted_finalize_count": len(interrupted),
        "current_utc_hour": current_hour,
        "policy": {
            "mutate_open_tails": False,
            "rewrite_raw": False,
            "delete_open_tails": False,
            "resume_fence": True,
        },
        "examples": [
            {
                "path": r["path"],
                "UTC_hour": r.get("UTC_hour"),
                "symbol": r.get("symbol"),
                "open_marker_present": r.get("open_marker_present"),
                "manifest_present": r.get("manifest_present"),
            }
            for r in open_rows[:16]
        ],
        "findings": findings,
        "silent_fallback": False,
    }
