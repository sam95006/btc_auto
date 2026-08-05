"""Corrected cross-partition linkage semantics for V11 recovery."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.nexus_microstructure.integrity_recovery_v11.path_identity import sort_key_for_partition


def audit_linkage_v11(partitions: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify previous_partition_id among *closed* partitions within (session, family, symbol).

    Fixes V1 false positives:
    - Missing manifest must not collapse symbols into one chain (path-inferred identity required).
    - Empty UTC_hour must not sort before real hours (use inferred hour).
    - Open tails are terminal markers, not checksum/linkage failures by themselves.
    - Claimed null is allowed for the first *closed* partition in a session chain
      and immediately after an open-tail / resume boundary.
    """
    by_key: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for p in partitions:
        key = (p.get("capture_session_id"), p.get("family"), p.get("symbol"))
        if not key[1] or not key[2]:
            # Still group unknowns separately to avoid cross-symbol contamination.
            key = (key[0], key[1] or "_UNKNOWN_FAMILY_", key[2] or f"_UNKNOWN_{p.get('partition_id')}")
        by_key[key].append(p)

    broken = 0
    checked = 0
    issues: list[dict[str, Any]] = []
    false_positive_avoided = 0

    for key, parts in by_key.items():
        ordered = sorted(parts, key=sort_key_for_partition)
        closed = [p for p in ordered if not p.get("is_open_tail") and p.get("manifest_present")]
        ids = {p.get("partition_id") for p in ordered}

        prev_closed_id: str | None = None
        saw_open_tail = False
        for p in ordered:
            checked += 1
            if p.get("is_open_tail") or not p.get("manifest_present"):
                # Open / unfinalized partition: do not enforce claimed previous against closed chain.
                if p.get("is_open_tail"):
                    saw_open_tail = True
                    false_positive_avoided += 1
                continue

            claimed = p.get("previous_partition_id")
            if prev_closed_id is None or saw_open_tail:
                # First closed after start or after open-tail/resume boundary may start a new chain.
                if claimed not in (None, "", "null") and claimed not in ids and claimed != prev_closed_id:
                    broken += 1
                    issues.append(
                        {
                            "partition_id": p.get("partition_id"),
                            "issue": "orphan_previous_partition_id",
                            "previous_partition_id": claimed,
                            "chain": list(key),
                        }
                    )
                prev_closed_id = p.get("partition_id")
                saw_open_tail = False
                continue

            if claimed != prev_closed_id:
                # If claimed is null but this is a legitimate rotation with missing link field → manifest bug
                broken += 1
                issues.append(
                    {
                        "partition_id": p.get("partition_id"),
                        "issue": "linkage_break",
                        "expected_previous": prev_closed_id,
                        "claimed_previous": claimed,
                        "chain": list(key),
                    }
                )
            prev_closed_id = p.get("partition_id")

        _ = closed  # explicit: open tails excluded from closed chain enforcement above

    status = "PASS" if broken == 0 else "FAIL"
    return {
        "cross_partition_linkage_status": status,
        "chains_checked": len(by_key),
        "partitions_checked": checked,
        "linkage_breaks": broken,
        "open_tail_linkage_exempt_count": false_positive_avoided,
        "issues": issues[:100],
        "semantics": "v11_closed_chain_with_open_tail_boundaries",
    }


def legacy_style_linkage_for_contrast(partitions: list[dict[str, Any]]) -> dict[str, Any]:
    """Reproduce V1 finalizer linkage (no path enrichment) for false-positive measurement."""
    by_key: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for p in partitions:
        key = (p.get("capture_session_id"), p.get("family"), p.get("symbol"))
        by_key[key].append(p)

    broken = 0
    checked = 0
    issues: list[dict[str, Any]] = []
    for _key, parts in by_key.items():
        ordered = sorted(parts, key=lambda x: (str(x.get("UTC_hour") or ""), str(x.get("partition_id") or "")))
        ids = {p.get("partition_id") for p in ordered}
        prev: str | None = None
        for p in ordered:
            checked += 1
            claimed = p.get("previous_partition_id")
            if prev is None:
                if claimed not in (None, "", "null") and claimed not in ids:
                    broken += 1
                    issues.append(
                        {
                            "partition_id": p.get("partition_id"),
                            "issue": "orphan_previous_partition_id",
                            "previous_partition_id": claimed,
                        }
                    )
            elif claimed != prev:
                broken += 1
                issues.append(
                    {
                        "partition_id": p.get("partition_id"),
                        "issue": "linkage_break",
                        "expected_previous": prev,
                        "claimed_previous": claimed,
                    }
                )
            prev = p.get("partition_id")
    return {
        "cross_partition_linkage_status": "PASS" if broken == 0 else "FAIL",
        "chains_checked": len(by_key),
        "partitions_checked": checked,
        "linkage_breaks": broken,
        "issues": issues[:50],
        "semantics": "v1_legacy",
    }
