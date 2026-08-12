"""Aggregated redteam / attack report for deep ingest contamination."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from backend.nexus_deep_ingest_contamination.archive_recovery import CorruptArchiveRecovery
from backend.nexus_deep_ingest_contamination.constants import SCHEMA_REDTEAM
from backend.nexus_deep_ingest_contamination.duplicate_ingest import DuplicateDatasetIngestor
from backend.nexus_deep_ingest_contamination.hard_bans import (
    refuse_formal_walk_forward,
    refuse_untouched_oos,
)
from backend.nexus_deep_ingest_contamination.provider_failover import build_default_failover_proofs
from backend.nexus_deep_ingest_contamination.revision_conflict import RevisionConflictHarness
from backend.nexus_deep_ingest_contamination.split_contamination import (
    run_deep_split_contamination_attacks,
)


def _finding(
    attack_id: str,
    *,
    blocked: bool,
    detail: str,
    severity: str = "CRITICAL",
) -> dict[str, Any]:
    return {
        "attack_id": attack_id,
        "severity": severity,
        "disposition": "FIXED" if blocked else "SURVIVOR",
        "attack_blocked": blocked,
        "survivor": not blocked,
        "detail": detail,
    }


def run_ingest_contamination_redteam() -> dict[str, Any]:
    """All deep ingest / contamination attacks — survivors must be 0."""
    findings: list[dict[str, Any]] = []

    # --- Corrupt archive recovery attacks ---
    with tempfile.TemporaryDirectory(prefix="v17_deep_rt_archive_") as tmp:
        archive = CorruptArchiveRecovery(Path(tmp))
        archive.pack_entry("good_1", {"v": 1})
        archive.pack_entry("bad_1", {"v": 2})
        archive.corrupt_entry_bytes("bad_1", mode="truncate")
        recovery = archive.recover()
        findings.append(
            _finding(
                "corrupt_archive_quarantine",
                blocked=(
                    recovery["quarantined_count"] >= 1
                    and recovery["status"] in {"RECOVERED_WITH_QUARANTINE", "BLOCKED_CORRUPT_ARCHIVE"}
                    and recovery["silent_corrupt_resume"] is False
                ),
                detail=f"status={recovery['status']} q={recovery['quarantined_count']}",
            )
        )
        silent = archive.attempt_silent_resume_over_corrupt("bad_1")
        findings.append(
            _finding(
                "silent_corrupt_resume_banned",
                blocked=silent.get("attack_blocked") is True,
                detail=str(silent.get("detail")),
            )
        )
        # Flip-bit corruption also quarantined
        archive.pack_entry("bad_2", {"v": 3})
        archive.corrupt_entry_bytes("bad_2", mode="flip")
        r2 = archive.verify_entry("bad_2")
        findings.append(
            _finding(
                "bitflip_archive_quarantine",
                blocked=r2.get("status") == "QUARANTINED",
                detail=str(r2.get("reason")),
            )
        )

    # --- Duplicate dataset ingestion ---
    dup = DuplicateDatasetIngestor()
    probe = dup.duplicate_attack_probe(
        dataset_id="ds_btc_fixture",
        payload={"rows": [{"ts": 1, "px": 100}], "schema": "fixture"},
    )
    findings.append(
        _finding(
            "duplicate_dataset_reingest",
            blocked=probe["attack_blocked"],
            detail=f"unique={probe['unique_hash_count']} log={probe['ingest_log_len']}",
        )
    )
    conflict = dup.ingest(
        dataset_id="ds_btc_fixture",
        payload={"rows": [{"ts": 1, "px": 999}], "schema": "fixture"},
        ingest_id="conflict_1",
    )
    findings.append(
        _finding(
            "dataset_id_hash_conflict",
            blocked=conflict.status == "REJECTED",
            detail=conflict.detail,
        )
    )

    # --- Revision conflicts ---
    harness = RevisionConflictHarness()
    conflict_proof = harness.build_conflict_fixture()
    findings.append(
        _finding(
            "revision_fork_ambiguous_tip",
            blocked=conflict_proof["attack_blocked"],
            detail=conflict_proof.get("detail") or "fork_refused",
        )
    )

    # --- Split contamination (includes baseline) ---
    split_rt = run_deep_split_contamination_attacks()
    findings.append(
        _finding(
            "dataset_split_contamination_survivors_zero",
            blocked=split_rt.get("survivor_count", 1) == 0,
            detail=f"survivors={split_rt.get('survivors')} attacks={split_rt.get('attack_count')}",
        )
    )

    # --- Provider failover ---
    failover = build_default_failover_proofs()
    findings.append(
        _finding(
            "rate_limit_and_outage_failover",
            blocked=failover.get("pass") is True,
            detail=(
                f"rate={failover['rate_limit_failover'].get('pass')} "
                f"outage={failover['outage_failover'].get('pass')}"
            ),
            severity="HIGH",
        )
    )

    # --- Hard bans ---
    wf = refuse_formal_walk_forward()
    oos = refuse_untouched_oos()
    findings.append(
        _finding(
            "formal_wf_and_oos_banned",
            blocked=wf["allowed"] is False and oos["allowed"] is False,
            detail=f"wf={wf['reason']}; oos={oos['reason']}",
        )
    )

    survivors = [f for f in findings if f["survivor"]]
    return {
        "schema": SCHEMA_REDTEAM,
        "attack_count": len(findings),
        "blocked_count": sum(1 for f in findings if f["attack_blocked"]),
        "survivor_count": len(survivors),
        "survivors": [f["attack_id"] for f in survivors],
        "findings": findings,
        "split_contamination": split_rt,
        "provider_failover": failover,
        "status": "PASS" if len(survivors) == 0 else "FAIL",
    }
