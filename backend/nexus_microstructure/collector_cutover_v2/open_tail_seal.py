"""Open-tail seal policy — define sealing without mutating prior raw campaigns."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_microstructure.collector_cutover_v2.constants import (
    RETAINED_CLASSIFICATION_COUNTS,
    SCHEMA,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Seal dispositions for EXPECTED_OPEN_TAIL partitions discovered forensically.
SEAL_DISPOSITIONS = (
    "LEAVE_UNSEALED_FORENSIC",  # prior campaign: retain as EXPECTED_OPEN_TAIL
    "SEAL_ON_GRACEFUL_STOP",  # new cutover writer: close() finalizes
    "RESUME_BOUNDARY",  # next session chains after open-tail fence
    "REQUIRES_FOUNDER_AUTH_TO_REBUILD_MANIFEST",
)


def open_tail_seal_policy(*, prior_open_tail_count: int = 113) -> dict[str, Any]:
    """Return the authoritative open-tail seal policy for Cutover V2.

    Hard rule: prior raw campaign partitions are never rewritten. New captures
    under cutover roots use atomic manifest seal + marker clear on graceful stop.
    """
    return {
        "schema": f"{SCHEMA}_open_tail_seal_policy",
        "created_at": _utc(),
        "prior_campaign_raw_modified": False,
        "prior_expected_open_tail_count": prior_open_tail_count,
        "retained_classification_counts": dict(RETAINED_CLASSIFICATION_COUNTS),
        "dispositions": list(SEAL_DISPOSITIONS),
        "policy": {
            "prior_campaign_open_tails": "LEAVE_UNSEALED_FORENSIC",
            "new_capture_graceful_stop": "SEAL_ON_GRACEFUL_STOP",
            "new_capture_kill_mid_write": "EXPECTED_OPEN_TAIL_or_INTERRUPTED_FINALIZE",
            "resume_after_open_tail": "RESUME_BOUNDARY",
            "manifest_rebuild": "REQUIRES_FOUNDER_AUTH_TO_REBUILD_MANIFEST",
        },
        "seal_protocol_v2": [
            "flush_buffers",
            "close_gzip_footer",
            "write_seal_state_FINALIZING",
            "atomic_manifest_replace",
            "write_seal_state_SEALED",
            "unlink_open_marker",
        ],
        "forbidden": [
            "silent_repair_of_prior_open_tails",
            "overwrite_prior_partition_bytes",
            "event_study_start_from_unsealed_prior",
            "claim_integrity_PASS_while_open_tails_unpolicyed",
        ],
        "integrity_status_with_prior_open_tails": "NOT_PASS_UNTIL_CUTOVER_AND_HOLD_GATES",
        "event_study": "NOT_READY",
    }


def classify_seal_action(
    *,
    is_prior_campaign: bool,
    graceful_stop: bool,
    open_marker_present: bool,
    manifest_present: bool,
) -> str:
    if is_prior_campaign:
        return "LEAVE_UNSEALED_FORENSIC"
    if graceful_stop and not open_marker_present and manifest_present:
        return "SEAL_ON_GRACEFUL_STOP"
    if open_marker_present and not manifest_present:
        return "RESUME_BOUNDARY"
    if manifest_present and open_marker_present:
        return "FINALIZE_MARKER_ORPHAN_REQUIRES_CLEANUP"
    return "UNKNOWN_REQUIRES_MORE_EVIDENCE"
