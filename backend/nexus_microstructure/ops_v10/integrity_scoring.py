"""Integrity scoring for Microstructure Operations V10."""
from __future__ import annotations

from typing import Any

from backend.nexus_microstructure.ops_v10.constants import SCHEMA


def score_campaign_integrity(
    *,
    finalizer_status: dict[str, Any] | None = None,
    checksum_replay_verified: bool | None = None,
    truncated_tail_detected: bool | None = None,
    cross_partition_linkage_status: str | None = None,
    partition_completeness_status: str | None = None,
    storage_cap_outcome: str | None = None,
    integrity_status: str | None = None,
) -> dict[str, Any]:
    """Produce a bounded integrity score from finalizer / audit fields.

    Does not run Event Study. Does not claim strategy readiness.
    """
    fs = finalizer_status or {}
    checksum_ok = (
        checksum_replay_verified
        if checksum_replay_verified is not None
        else bool(fs.get("checksum_replay_verified"))
    )
    truncated = (
        truncated_tail_detected
        if truncated_tail_detected is not None
        else bool(fs.get("truncated_tail_detected"))
    )
    linkage = cross_partition_linkage_status or fs.get("cross_partition_linkage_status") or "UNKNOWN"
    completeness = partition_completeness_status or fs.get("partition_completeness_status") or "UNKNOWN"
    storage = storage_cap_outcome or fs.get("storage_cap_outcome") or "UNKNOWN"
    integrity = integrity_status or fs.get("integrity_status") or "UNKNOWN"

    deductions: list[str] = []
    score = 100
    if not checksum_ok:
        score -= 30
        deductions.append("checksum_replay_not_verified")
    if truncated:
        score -= 25
        deductions.append("truncated_tail_detected")
    if linkage != "PASS":
        score -= 20
        deductions.append("cross_partition_linkage_not_pass")
    if completeness != "COMPLETE":
        score -= 15
        deductions.append("partition_set_incomplete")
    if storage == "HARD_CAP_HIT":
        score -= 10
        deductions.append("hard_storage_cap_hit")
    if integrity != "PASS":
        score -= 20
        deductions.append("integrity_status_not_pass")
        # Avoid double-count when integrity already FAIL for same causes
        score = max(score, 0)

    score = max(0, min(100, score))
    if score >= 90 and integrity == "PASS":
        band = "HIGH"
        overall = "PASS"
    elif score >= 60:
        band = "MEDIUM"
        overall = "DEGRADED"
    else:
        band = "LOW"
        overall = "FAIL"

    return {
        "schema": f"{SCHEMA}_integrity_score",
        "integrity_score": score,
        "integrity_band": band,
        "integrity_overall": overall,
        "integrity_status": integrity,
        "deductions": deductions,
        "inputs": {
            "checksum_replay_verified": checksum_ok,
            "truncated_tail_detected": truncated,
            "cross_partition_linkage_status": linkage,
            "partition_completeness_status": completeness,
            "storage_cap_outcome": storage,
            "integrity_status": integrity,
        },
        "event_study_readiness_status": "NOT_READY",
        "event_study_real_execution": False,
        "new_strategy_generated_count": 0,
    }
