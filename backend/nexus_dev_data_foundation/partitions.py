"""Time partitions: DEVELOPMENT / VALIDATION_PLANNING / OOS_RESERVED / OOS_UNTOUCHED."""
from __future__ import annotations

from typing import Any

from backend.nexus_dev_data_foundation.constants import (
    DEV_END_MS,
    DEV_START_MS,
    HOLDOUT_CONSUMED_END_MS,
    HOLDOUT_CONSUMED_START_MS,
    PARTITION_CATEGORIES,
    PARTITION_SCHEMA,
    SEPTEMBER_OOS_END_MS,
    SEPTEMBER_OOS_START_MS,
)
from backend.nexus_dev_data_foundation.hashing import ms_to_iso, sha_obj


def build_time_partitions() -> dict[str, Any]:
    """Seal non-overlapping partitions. OOS is catalogued but never consumable."""
    span = DEV_END_MS - DEV_START_MS
    split = DEV_START_MS + int(span * 0.60)

    partitions = [
        {
            "partition_id": "DEV_EXPLORATION_PRIMARY",
            "category": "DEVELOPMENT",
            "start_ms": DEV_START_MS,
            "end_ms": split - 1,
            "start_utc": ms_to_iso(DEV_START_MS),
            "end_utc": ms_to_iso(split - 1),
            "consumable_for_development": True,
            "consumable_for_validation_planning": False,
            "oos_consumable": False,
            "notes": "Primary development exploration window (first 60% of research V2/V3 span)",
        },
        {
            "partition_id": "VALIDATION_PLANNING_PRIMARY",
            "category": "VALIDATION_PLANNING",
            "start_ms": split,
            "end_ms": DEV_END_MS,
            "start_utc": ms_to_iso(split),
            "end_utc": ms_to_iso(DEV_END_MS),
            "consumable_for_development": False,
            "consumable_for_validation_planning": True,
            "oos_consumable": False,
            "notes": "Validation planning only - not formal walk-forward, not OOS",
        },
        {
            "partition_id": "SEPTEMBER_H3_OOS_RESERVED",
            "category": "OOS_RESERVED",
            "start_ms": SEPTEMBER_OOS_START_MS,
            "end_ms": SEPTEMBER_OOS_END_MS,
            "start_utc": ms_to_iso(SEPTEMBER_OOS_START_MS),
            "end_utc": ms_to_iso(SEPTEMBER_OOS_END_MS),
            "consumable_for_development": False,
            "consumable_for_validation_planning": False,
            "oos_consumable": False,
            "notes": "Reserved September OOS - sealed, never consumed by V15-A",
        },
        {
            "partition_id": "POST_SEPTEMBER_OOS_UNTOUCHED",
            "category": "OOS_UNTOUCHED",
            "start_ms": SEPTEMBER_OOS_END_MS + 1,
            "end_ms": SEPTEMBER_OOS_END_MS + 365 * 86_400_000,
            "start_utc": ms_to_iso(SEPTEMBER_OOS_END_MS + 1),
            "end_utc": ms_to_iso(SEPTEMBER_OOS_END_MS + 365 * 86_400_000),
            "consumable_for_development": False,
            "consumable_for_validation_planning": False,
            "oos_consumable": False,
            "notes": "Future untouched OOS reservation - do not open",
        },
    ]

    # Document consumed holdout as forbidden (not a usable partition category).
    forbidden = [
        {
            "interval_id": "H3_CONSUMED_FAILED_HOLDOUT",
            "category": "CONSUMED_FORBIDDEN",
            "start_ms": HOLDOUT_CONSUMED_START_MS,
            "end_ms": HOLDOUT_CONSUMED_END_MS,
            "start_utc": ms_to_iso(HOLDOUT_CONSUMED_START_MS),
            "end_utc": ms_to_iso(HOLDOUT_CONSUMED_END_MS),
            "consumable_for_development": False,
            "oos_consumable": False,
            "notes": "Prior consumed failed holdout - immutable, never reuse as qualification",
        }
    ]

    cats = {p["category"] for p in partitions}
    assert cats == set(PARTITION_CATEGORIES), f"missing categories: {set(PARTITION_CATEGORIES) - cats}"

    payload = {
        "schema": PARTITION_SCHEMA,
        "partitions": partitions,
        "forbidden_consumed_intervals": forbidden,
        "categories": list(PARTITION_CATEGORIES),
        "oos_consumed": False,
        "oos_executed": False,
        "formal_walk_forward": False,
        "overlap_policy": "DEVELOPMENT_and_VALIDATION_PLANNING_are_adjacent_non_overlapping;"
        "OOS_RESERVED_and_OOS_UNTOUCHED_never_loadable_for_development",
    }
    payload["partition_checksum"] = sha_obj(
        {
            "partitions": [
                {
                    "partition_id": p["partition_id"],
                    "category": p["category"],
                    "start_ms": p["start_ms"],
                    "end_ms": p["end_ms"],
                }
                for p in partitions
            ],
            "forbidden": [
                {
                    "interval_id": f["interval_id"],
                    "start_ms": f["start_ms"],
                    "end_ms": f["end_ms"],
                }
                for f in forbidden
            ],
        }
    )
    return payload


def classify_timestamp(ts_ms: int, partitions: dict[str, Any] | None = None) -> str:
    """Return partition category for a timestamp, or OUTSIDE_SEALED_PARTITIONS."""
    parts = (partitions or build_time_partitions())["partitions"]
    for p in parts:
        if int(p["start_ms"]) <= int(ts_ms) <= int(p["end_ms"]):
            return str(p["category"])
    forb = (partitions or build_time_partitions()).get("forbidden_consumed_intervals") or []
    for f in forb:
        if int(f["start_ms"]) <= int(ts_ms) <= int(f["end_ms"]):
            return "CONSUMED_FORBIDDEN"
    return "OUTSIDE_SEALED_PARTITIONS"


def assert_not_oos_consumable(category: str) -> None:
    if category in {"OOS_RESERVED", "OOS_UNTOUCHED", "CONSUMED_FORBIDDEN"}:
        raise ValueError(f"oos_or_consumed_forbidden:{category}")


def partitions_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return not (int(a["end_ms"]) < int(b["start_ms"]) or int(a["start_ms"]) > int(b["end_ms"]))


def verify_no_dev_oos_overlap(partitions: dict[str, Any] | None = None) -> dict[str, Any]:
    parts = (partitions or build_time_partitions())["partitions"]
    by_cat = {p["category"]: p for p in parts}
    violations: list[str] = []
    for oos_cat in ("OOS_RESERVED", "OOS_UNTOUCHED"):
        for use_cat in ("DEVELOPMENT", "VALIDATION_PLANNING"):
            if partitions_overlap(by_cat[use_cat], by_cat[oos_cat]):
                violations.append(f"{use_cat}_overlaps_{oos_cat}")
    # DEVELOPMENT vs VALIDATION_PLANNING must be adjacent but not overlapping
    if partitions_overlap(by_cat["DEVELOPMENT"], by_cat["VALIDATION_PLANNING"]):
        violations.append("DEVELOPMENT_overlaps_VALIDATION_PLANNING")
    return {
        "ok": len(violations) == 0,
        "violations": violations,
        "oos_consumed": False,
    }
