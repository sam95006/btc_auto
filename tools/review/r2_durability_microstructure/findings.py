"""Static + adversarial findings aggregation for Founder R2."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


STATIC_FINDINGS: list[dict[str, Any]] = [
    {
        "id": "R2-C-001",
        "lane": "C",
        "severity": "CRITICAL",
        "title": "Snapshot authority skips payload-hash verification",
        "area": "snapshot_authority",
        "detail": (
            "RuntimeDurabilityV2.create_snapshot verifies hash-chain material and PRAGMA "
            "integrity_check only. flip_bit_in_payload corruption is detected by "
            "detect_corruption but still yields SNAPSHOT_OK and advances LKG."
        ),
        "evidence_refs": ["snapshot_skips_payload_corruption"],
        "remediation": (
            "Require detect_corruption(deep=True) (or at least payload_hash recompute) inside "
            "create_snapshot before writing LKG/checkpoint."
        ),
    },
    {
        "id": "R2-C-002",
        "lane": "C",
        "severity": "CRITICAL",
        "title": "Snapshot manifest can claim a ledger position ahead of checksummed bytes",
        "area": "ledger_sequence_authority / snapshot_authority",
        "detail": (
            "source_ledger_position / max_sequence are read from the live connection after "
            "copying the main sqlite file. A concurrent append can advance the claimed "
            "position while file_sha256 covers only the main file. restore_last_known_good "
            "copies the main snapshot path and does not apply companion -wal bytes."
        ),
        "evidence_refs": ["snapshot_from_stale_ledger_tail"],
        "remediation": (
            "Quiesce writers (exclusive lock), wal_checkpoint(TRUNCATE), copy, then derive "
            "position strictly from the snapshot file contents; include wal in checksum or "
            "forbid non-empty wal beside snapshots."
        ),
    },
    {
        "id": "R2-D-001",
        "lane": "D",
        "severity": "CRITICAL",
        "title": "Duplicate partition identity silently overwrites capture files",
        "area": "partition_finalization / storage_safety",
        "detail": (
            "DurablePartitionWriterV11 builds partition paths from session+family+symbol+"
            "hour+local_seq with gzip.open(..., 'wb') and no O_EXCL / identity registry. "
            "Two writers with the same capture_session_id collide on one path."
        ),
        "evidence_refs": ["duplicate_partition_identity"],
        "remediation": (
            "Use exclusive file create, writer fencing tokens, or a session-scoped partition "
            "allocator that refuses duplicate partition_id."
        ),
    },
    {
        "id": "R2-C-003",
        "lane": "C",
        "severity": "HIGH",
        "title": "Clock-rollback guard is process-local only",
        "area": "ledger_sequence_authority",
        "detail": (
            "_last_accepted_wall lives only in memory. Reopening DurableEventLedgerV2 accepts "
            "a wall_clock earlier than the last persisted event without BLOCKED_CLOCK_ROLLBACK."
        ),
        "evidence_refs": ["clock_rollback_lost_on_reopen"],
        "remediation": "Persist last_accepted_wall in ledger_meta and enforce on open/append.",
    },
    {
        "id": "R2-C-004",
        "lane": "C",
        "severity": "HIGH",
        "title": "Fsync-interruption drill is a false durability proof",
        "area": "checkpoint_authority / storage_safety",
        "detail": (
            "_maybe_fsync raises InterruptedError after commit. The DR injection matrix marks "
            "the exception as PASS, yet event_count shows the row already durable in WAL."
        ),
        "evidence_refs": ["fsync_interrupt_commits_anyway"],
        "remediation": (
            "Model true pre-commit / mid-page faults; do not treat post-commit exceptions as "
            "evidence of fail-closed durability."
        ),
    },
    {
        "id": "R2-C-005",
        "lane": "C",
        "severity": "HIGH",
        "title": "Checkpoint file lacks snapshot/LKG seal",
        "area": "checkpoint_authority",
        "detail": (
            "checkpoint_v2.json can be written independently of create_snapshot. A premature "
            "checkpoint may exist with no LKG and without proving ledger fsync."
        ),
        "evidence_refs": ["checkpoint_before_ledger_fsync"],
        "remediation": (
            "Make checkpoint emission atomic with LKG generation + snapshot checksum; reject "
            "unbound checkpoint files on recover()."
        ),
    },
    {
        "id": "R2-C-006",
        "lane": "C",
        "severity": "HIGH",
        "title": "Concurrent snapshot vs append races on WAL copy",
        "area": "snapshot_authority",
        "detail": (
            "Under concurrent append, create_snapshot may raise PermissionError while copying "
            "-wal/-shm on Windows, or succeed in a torn state. Writers are not fenced."
        ),
        "evidence_refs": ["concurrent_snapshot_wal_lock"],
        "remediation": "Exclusive snapshot lock + checkpoint(TRUNCATE) before copy; no live writers.",
    },
    {
        "id": "R2-D-002",
        "lane": "D",
        "severity": "HIGH",
        "title": "Orphan .open marker after finalize is unclassified",
        "area": "open-tail_semantics / partition_finalization",
        "detail": (
            "Finalize order is gzip close → manifest replace → unlink .open. Crash between "
            "replace and unlink leaves manifest_present + open_marker_present with integrity OK "
            "and finding_count=0."
        ),
        "evidence_refs": ["orphan_open_marker_after_finalize"],
        "remediation": (
            "Classify open_marker_present∧manifest_present as FINALIZE_MARKER_ORPHAN / ambiguous; "
            "or unlink marker before publishing manifest via two-phase state."
        ),
    },
    {
        "id": "R2-D-003",
        "lane": "D",
        "severity": "HIGH",
        "title": "Exchange clock rollback across hour rotation breaks linkage",
        "area": "cross-partition_linkage / clock",
        "detail": (
            "Writer accepts exchange_timestamp moving into a prior UTC hour and chains "
            "previous_partition_id forward. Hour-sorted audit_linkage_v11 then reports FAIL."
        ),
        "evidence_refs": ["clock_rollback_across_partition_rotation"],
        "remediation": (
            "Refuse backward hour rotation without explicit resume boundary; or treat "
            "hour regression as open-tail/resume fence in linkage."
        ),
    },
    {
        "id": "R2-D-004",
        "lane": "D",
        "severity": "HIGH",
        "title": "Gzip-closed finalize interrupt not modeled as open-tail",
        "area": "open-tail_semantics / checksum_semantics",
        "detail": (
            "is_open_tail requires truncated_tail∧¬manifest_present. After a successful gzip "
            "close but before manifest write, replay is OK with .open retained → MANIFEST_BUG "
            "only; open marker is not an authority signal."
        ),
        "evidence_refs": ["power_loss_during_gzip_close"],
        "remediation": (
            "Treat open_marker_present∧¬manifest_present as INTERRUPTED_FINALIZE regardless of "
            "gzip replay status."
        ),
    },
    {
        "id": "R2-D-005",
        "lane": "D",
        "severity": "MEDIUM",
        "title": "No storage gate blocks migration of open partitions",
        "area": "migration_provenance / storage_safety",
        "detail": (
            "Classifier can label MIGRATION_ARTIFACT when sizes match, but nothing prevents "
            "copying in-flight partitions with .open markers."
        ),
        "evidence_refs": ["partition_migrated_while_open"],
        "remediation": "Migration/export tools must refuse trees containing *.jsonl.gz.open markers.",
    },
    {
        "id": "R2-C-007",
        "lane": "C",
        "severity": "MEDIUM",
        "title": "SQLite synchronous=NORMAL weakens power-loss guarantees",
        "area": "storage_safety",
        "detail": (
            "DurableEventLedgerV2 sets PRAGMA synchronous=NORMAL. Combined with post-commit "
            "PASSIVE checkpoint, power-loss durability is weaker than the DR narrative implies."
        ),
        "evidence_refs": ["static:ledger.py"],
        "remediation": "Use FULL/EXTRA for authority ledgers or document soft-durability explicitly.",
    },
]


CONTROL_STRENGTHS: list[dict[str, Any]] = [
    {
        "id": "R2-CTRL-001",
        "lane": "C",
        "title": "Corrupted LKG fails closed",
        "evidence_refs": ["restore_from_corrupted_lkg"],
    },
    {
        "id": "R2-CTRL-002",
        "lane": "D",
        "title": "V11 writer finalizes gzip before atomic manifest replace",
        "evidence_refs": ["manifest_before_file_close"],
    },
    {
        "id": "R2-CTRL-003",
        "lane": "D",
        "title": "Missing mid-chain previous_partition_id fails linkage audit",
        "evidence_refs": ["missing_previous_link"],
    },
    {
        "id": "R2-CTRL-004",
        "lane": "D",
        "title": "Kill-before-gzip-footer yields EXPECTED_OPEN_TAIL without silent repair",
        "evidence_refs": ["power_loss_during_gzip_close"],
    },
    {
        "id": "R2-CTRL-005",
        "lane": "C",
        "title": "Live-ahead-of-LKG restore blocked as ambiguous (Lane C tests)",
        "evidence_refs": ["tests/test_runtime_durability_dr_v2.py::test_live_ahead_of_lkg_blocks_without_evidence_loss_claim"],
    },
]


def integration_recommendation(findings: list[dict[str, Any]], matrix: dict[str, Any]) -> dict[str, Any]:
    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    high = [f for f in findings if f["severity"] == "HIGH"]
    if critical:
        decision = "DO_NOT_INTEGRATE_AS_AUTHORITY_UNTIL_CRITICAL_FIXED"
        rationale = (
            "Critical gaps in snapshot payload verification, racy snapshot position, and "
            "duplicate partition identity mean Lane C/D must not be treated as sole durability / "
            "partition authorities in the V11 controlled integration spine yet."
        )
    elif high:
        decision = "CONDITIONAL_INTEGRATE_WITH_BLOCKERS"
        rationale = "No criticals remain but high findings require tracked remediation before promotion."
    else:
        decision = "INTEGRATION_READY_WITH_MONITORING"
        rationale = "No critical/high findings from R2 adversarial matrix."

    return {
        "integration_recommendation": decision,
        "rationale": rationale,
        "critical_count": len(critical),
        "high_count": len(high),
        "blocking_finding_ids": [f["id"] for f in critical + high],
        "allowed_now": [
            "Keep Lane C/D code on feature branches for further hardening",
            "Retain forensic/open-tail classification improvements from Lane D as non-authority helpers",
            "Do not declare campaign Event Study READY based on V11 recovery alone",
        ],
        "required_before_authority_integration": [
            "R2-C-001 snapshot payload verify",
            "R2-C-002 snapshot position from checksummed bytes + restore wal policy",
            "R2-D-001 exclusive partition identity",
            "R2-C-003 persist clock rollback watermark",
            "R2-D-002 orphan open-marker classification",
        ],
        "hazard_confirmed_count": matrix.get("hazard_confirmed_count"),
        "pass_id": matrix.get("pass_id"),
    }


def build_findings_report(
    *,
    matrix_pass1: dict[str, Any],
    matrix_pass2: dict[str, Any] | None = None,
    origin_commits: dict[str, str] | None = None,
) -> dict[str, Any]:
    findings = list(STATIC_FINDINGS)
    # Attach live confirmation from latest matrix
    latest = matrix_pass2 or matrix_pass1
    by_id = {r["scenario_id"]: r for r in latest.get("results", [])}
    for f in findings:
        refs = f.get("evidence_refs") or []
        live = []
        for ref in refs:
            if ref in by_id:
                live.append(
                    {
                        "scenario_id": ref,
                        "hazard_confirmed": by_id[ref].get("hazard_confirmed"),
                        "control_ok": by_id[ref].get("control_ok"),
                    }
                )
        f["live_confirmation"] = live

    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    high = [f for f in findings if f["severity"] == "HIGH"]
    medium = [f for f in findings if f["severity"] == "MEDIUM"]

    rec = integration_recommendation(findings, latest)

    return {
        "schema": "v11_review_durability_microstructure_findings_v1",
        "review": "FOUNDER_R2_DURABILITY_MICROSTRUCTURE",
        "generated_at": _utc(),
        "origin": origin_commits or {},
        "pass1": {
            "hazard_confirmed_count": matrix_pass1.get("hazard_confirmed_count"),
            "control_ok_count": matrix_pass1.get("control_ok_count"),
            "total_scenarios": matrix_pass1.get("total_scenarios"),
        },
        "pass2": None
        if matrix_pass2 is None
        else {
            "hazard_confirmed_count": matrix_pass2.get("hazard_confirmed_count"),
            "control_ok_count": matrix_pass2.get("control_ok_count"),
            "total_scenarios": matrix_pass2.get("total_scenarios"),
            "delta_vs_pass1": {
                "hazard_confirmed_count": (matrix_pass2.get("hazard_confirmed_count") or 0)
                - (matrix_pass1.get("hazard_confirmed_count") or 0),
            },
        },
        "critical_findings": critical,
        "high_findings": high,
        "medium_findings": medium,
        "control_strengths": CONTROL_STRENGTHS,
        "remaining_blockers": [f["id"] for f in critical + high],
        "integration_recommendation": rec,
        "raw_campaign_evidence_modified": False,
        "false_pass_watchlist": [
            "Lane C injection matrix fsync_interruption PASS",
            "SNAPSHOT_OK after payload bit flip",
            "LKG pointer position vs checksummed main-file row count",
            "Classifier silence on orphan .open + manifest",
        ],
    }
