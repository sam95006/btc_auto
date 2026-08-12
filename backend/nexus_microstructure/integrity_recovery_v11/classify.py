"""Discover partitions and classify integrity findings (non-destructive)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.integrity_recovery_v11.checksum import (
    compare_checksum,
    replay_gzip_sha256,
)
from backend.nexus_microstructure.integrity_recovery_v11.path_identity import infer_identity_from_path
from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import (
    manifest_path_for,
    open_marker_for,
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def discover_partitions_v11(partitions_root: Path) -> list[dict[str, Any]]:
    """Scan partition tree; enrich identity from path when manifest absent."""
    found: list[dict[str, Any]] = []
    partitions_root = Path(partitions_root)
    if not partitions_root.is_dir():
        return found

    for gz in sorted(partitions_root.rglob("*.jsonl.gz")):
        man_path = manifest_path_for(gz)
        # Also accept V1 writer naming (*.jsonl.manifest.json)
        alt = gz.with_suffix(".manifest.json")
        if not man_path.is_file() and alt.is_file():
            man_path = alt

        manifest: dict[str, Any] = {}
        manifest_present = man_path.is_file()
        if manifest_present:
            try:
                manifest = _load_json(man_path)
            except Exception as exc:  # noqa: BLE001
                manifest = {"_manifest_load_error": f"{type(exc).__name__}:{exc}"}

        identity = infer_identity_from_path(gz, manifest)
        replay = replay_gzip_sha256(gz)
        expected = (
            manifest.get("rolling_checksum")
            or manifest.get("checksum")
            or manifest.get("replayed_checksum")
        )
        cmp = compare_checksum(expected, replay.get("replayed_checksum"))
        open_marker = open_marker_for(gz).is_file()
        truncated = bool(replay.get("truncated_tail"))
        # Classic open-tail: truncated gzip without manifest.
        is_open_tail = truncated and not manifest_present
        # R2-D-004: .open retained without manifest is interrupted finalize authority signal.
        interrupted_finalize = open_marker and not manifest_present
        # R2-D-002: manifest published but .open orphaned after finalize.
        finalize_marker_orphan = open_marker and manifest_present

        integrity = replay["integrity_status"]
        if integrity == "OK" and expected and cmp["checksum_match"] is False:
            integrity = "CHECKSUM_MISMATCH"
        elif is_open_tail:
            integrity = "OPEN_TAIL_UNFINALIZED"
        elif interrupted_finalize and integrity == "OK":
            integrity = "INTERRUPTED_FINALIZE"

        found.append(
            {
                "path": str(gz),
                "manifest_path": str(man_path) if manifest_present else None,
                "partition_id": identity["partition_id"],
                "exchange": manifest.get("exchange"),
                "family": identity.get("family"),
                "symbol": identity.get("symbol"),
                "UTC_hour": identity.get("UTC_hour"),
                "partition_seq": identity.get("partition_seq"),
                "record_count": int(manifest.get("record_count") or 0),
                "first_exchange_timestamp": manifest.get("first_exchange_timestamp"),
                "last_exchange_timestamp": manifest.get("last_exchange_timestamp"),
                "previous_partition_id": manifest.get("previous_partition_id"),
                "capture_session_id": identity.get("capture_session_id"),
                "rolling_checksum": expected,
                "replayed_checksum": replay.get("replayed_checksum"),
                "partial_sha256": replay.get("partial_sha256"),
                "partial_line_count": replay.get("partial_line_count"),
                "checksum_match": cmp["checksum_match"] if expected else None,
                "integrity_status": integrity,
                "truncated_tail": truncated,
                "is_open_tail": is_open_tail,
                "interrupted_finalize": interrupted_finalize,
                "finalize_marker_orphan": finalize_marker_orphan,
                "open_marker_present": open_marker,
                "compressed_bytes": gz.stat().st_size if gz.is_file() else 0,
                "manifest_present": manifest_present,
                "original_sha256_file": _file_sha256(gz),
            }
        )
    return found


def _file_sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def classify_partition(
    p: dict[str, Any],
    *,
    chain_is_last: bool,
    legacy_checksum_listed: bool,
    legacy_linkage_listed: bool,
    source_size_matches: bool | None = None,
) -> dict[str, Any]:
    """Assign taxonomy label(s) for one partition finding."""
    labels: list[str] = []
    evidence: list[str] = []

    if p.get("is_open_tail") and chain_is_last:
        labels.append("EXPECTED_OPEN_TAIL")
        evidence.append("gzip_EOF_without_manifest_last_in_session_symbol_chain")
        if legacy_checksum_listed:
            labels.append("FINALIZER_FALSE_POSITIVE")
            evidence.append("v1_checksum_failures_list_includes_open_tail")
        if legacy_linkage_listed:
            labels.append("LINKAGE_SEMANTICS_BUG")
            evidence.append("v1_linkage_chained_across_missing_identity_or_open_tail")
    elif p.get("truncated_tail") and not chain_is_last:
        labels.append("ACTUAL_DATA_CORRUPTION")
        evidence.append("gzip_EOF_with_later_ok_partition_same_session_symbol")
    elif p.get("truncated_tail") and p.get("manifest_present"):
        labels.append("ACTUAL_DATA_CORRUPTION")
        evidence.append("manifest_claims_finalized_but_gzip_truncated")

    # R2-D-004: open marker + no manifest ⇒ interrupted finalize (even if gzip replay OK).
    if p.get("interrupted_finalize") or (
        p.get("open_marker_present") and not p.get("manifest_present")
    ):
        if "EXPECTED_OPEN_TAIL" not in labels:
            labels.append("INTERRUPTED_FINALIZE")
            evidence.append("open_marker_present_without_manifest")
        elif "INTERRUPTED_FINALIZE" not in labels and not p.get("truncated_tail"):
            labels.append("INTERRUPTED_FINALIZE")
            evidence.append("open_marker_present_without_manifest")

    # R2-D-002: manifest present + orphan .open after finalize.
    if p.get("finalize_marker_orphan") or (
        p.get("open_marker_present") and p.get("manifest_present") and not p.get("truncated_tail")
    ):
        labels.append("FINALIZE_MARKER_ORPHAN")
        evidence.append("open_marker_retained_after_manifest_publish")

    if (
        not p.get("truncated_tail")
        and not p.get("open_marker_present")
        and p.get("integrity_status") == "OK"
        and not p.get("manifest_present")
    ):
        labels.append("MANIFEST_BUG")
        evidence.append("gzip_ok_but_manifest_missing_finalize_race")
    elif (
        not p.get("truncated_tail")
        and p.get("open_marker_present")
        and not p.get("manifest_present")
        and p.get("integrity_status") in ("OK", "INTERRUPTED_FINALIZE")
        and "INTERRUPTED_FINALIZE" not in labels
    ):
        labels.append("INTERRUPTED_FINALIZE")
        evidence.append("gzip_ok_open_marker_no_manifest")

    if p.get("checksum_match") is False and p.get("integrity_status") == "CHECKSUM_MISMATCH":
        labels.append("ACTUAL_DATA_CORRUPTION")
        evidence.append("rolling_checksum_mismatch_on_intact_gzip")

    if source_size_matches is True and p.get("is_open_tail"):
        labels.append("MIGRATION_ARTIFACT")
        evidence.append("finalize_root_byte_identical_to_source_open_tail_not_copy_corruption")

    if legacy_linkage_listed and not p.get("manifest_present"):
        if "LINKAGE_SEMANTICS_BUG" not in labels:
            labels.append("LINKAGE_SEMANTICS_BUG")
            evidence.append("missing_manifest_null_identity_collapsed_v1_chains")

    if not labels:
        return {
            "partition_id": p.get("partition_id"),
            "classifications": [],
            "primary_classification": None,
            "evidence": ["intact_closed_partition"],
            "failure": False,
        }

    # Prefer most severe primary
    priority = [
        "ACTUAL_DATA_CORRUPTION",
        "INTERRUPTED_FINALIZE",
        "FINALIZE_MARKER_ORPHAN",
        "MANIFEST_BUG",
        "EXPECTED_OPEN_TAIL",
        "MIGRATION_ARTIFACT",
        "LINKAGE_SEMANTICS_BUG",
        "FINALIZER_FALSE_POSITIVE",
        "UNKNOWN_REQUIRES_MORE_EVIDENCE",
    ]
    primary = next((c for c in priority if c in labels), labels[0])

    return {
        "partition_id": p.get("partition_id"),
        "classifications": labels,
        "primary_classification": primary,
        "evidence": evidence,
        "failure": True,
    }


def classify_campaign_partitions(
    partitions: list[dict[str, Any]],
    *,
    legacy_checksum_ids: set[str] | None = None,
    legacy_linkage_ids: set[str] | None = None,
    source_size_match: dict[str, bool] | None = None,
) -> dict[str, Any]:
    legacy_checksum_ids = legacy_checksum_ids or set()
    legacy_linkage_ids = legacy_linkage_ids or set()
    source_size_match = source_size_match or {}

    # Determine last partition per (session, family, symbol)
    from collections import defaultdict

    from backend.nexus_microstructure.integrity_recovery_v11.path_identity import sort_key_for_partition

    by_key: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for p in partitions:
        by_key[(p.get("capture_session_id"), p.get("family"), p.get("symbol"))].append(p)
    last_ids: set[str] = set()
    for parts in by_key.values():
        ordered = sorted(parts, key=sort_key_for_partition)
        if ordered:
            last_ids.add(str(ordered[-1].get("partition_id")))

    findings: list[dict[str, Any]] = []
    counts: dict[str, int] = {
        "ACTUAL_DATA_CORRUPTION": 0,
        "EXPECTED_OPEN_TAIL": 0,
        "INTERRUPTED_FINALIZE": 0,
        "FINALIZE_MARKER_ORPHAN": 0,
        "MIGRATION_ARTIFACT": 0,
        "MANIFEST_BUG": 0,
        "FINALIZER_FALSE_POSITIVE": 0,
        "LINKAGE_SEMANTICS_BUG": 0,
        "UNKNOWN_REQUIRES_MORE_EVIDENCE": 0,
    }

    for p in partitions:
        pid = str(p.get("partition_id"))
        # Only classify failure-like partitions
        failure_like = (
            p.get("is_open_tail")
            or p.get("truncated_tail")
            or p.get("interrupted_finalize")
            or p.get("finalize_marker_orphan")
            or p.get("open_marker_present")
            or (not p.get("manifest_present") and p.get("integrity_status") in ("OK", "INTERRUPTED_FINALIZE"))
            or p.get("checksum_match") is False
            or pid in legacy_checksum_ids
            or pid in legacy_linkage_ids
        )
        if not failure_like:
            continue
        row = classify_partition(
            p,
            chain_is_last=pid in last_ids,
            legacy_checksum_listed=pid in legacy_checksum_ids,
            legacy_linkage_listed=pid in legacy_linkage_ids,
            source_size_matches=source_size_match.get(pid),
        )
        if not row["failure"] and not row["classifications"]:
            continue
        findings.append(row)
        for c in row["classifications"]:
            counts[c] = counts.get(c, 0) + 1

    primary_counts: dict[str, int] = {k: 0 for k in counts}
    for f in findings:
        pc = f.get("primary_classification")
        if pc:
            primary_counts[pc] = primary_counts.get(pc, 0) + 1

    return {
        "finding_count": len(findings),
        "classification_counts": counts,
        "primary_classification_counts": primary_counts,
        "findings": findings,
        "note": (
            "classification_counts are multi-label (one partition may carry several labels); "
            "primary_classification_counts are mutually exclusive per finding."
        ),
    }
