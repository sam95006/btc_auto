"""PIT development data records — full provenance, no invented history."""
from __future__ import annotations

from typing import Any

from backend.nexus_dev_data_foundation.constants import (
    AVAILABILITY_STATES,
    HARD_BAN_FLAGS,
    RECORD_SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_dev_data_foundation.hashing import ms_to_iso, sha_obj, utc_now_iso
from backend.nexus_dev_data_foundation.lineage import build_lineage
from backend.nexus_dev_data_foundation.partitions import assert_not_oos_consumable


REQUIRED_RECORD_KEYS: tuple[str, ...] = (
    "schema",
    "schema_version",
    "record_id",
    "source_id",
    "source_kind",
    "source_path",
    "source_timestamp",
    "availability_timestamp",
    "availability_ms",
    "retrieval_timestamp",
    "lineage",
    "content_checksum",
    "availability_state",
    "staleness_state",
    "missing_state",
    "partition_id",
    "partition_category",
    "oos_consumed",
    "invented_history",
    "record_hash",
)


class DevDataRecordError(ValueError):
    pass


def _staleness_state(*, availability_ms: int | None, retrieval_timestamp: str, max_age_ms: int | None) -> str:
    if availability_ms is None:
        return "UNKNOWN"
    # Fixtures / manifests: staleness is descriptive relative to sealed availability, not live clock.
    if max_age_ms is None:
        return "SEALED_NOT_LIVE"
    return "FRESH" if max_age_ms >= 0 else "STALE"


def build_record(
    *,
    source_id: str,
    source_kind: str,
    source_path: str | None,
    source_timestamp: str | None,
    availability_ms: int | None,
    content_checksum: str,
    availability_state: str,
    partition_id: str | None,
    partition_category: str,
    missing_state: str = "NOT_MISSING",
    retrieval_timestamp: str | None = None,
    notes: str | None = None,
    payload_summary: dict[str, Any] | None = None,
    allow_oos_catalog_only: bool = False,
) -> dict[str, Any]:
    if availability_state not in AVAILABILITY_STATES:
        raise DevDataRecordError(f"invalid_availability_state:{availability_state}")
    if not allow_oos_catalog_only:
        assert_not_oos_consumable(partition_category)
    elif partition_category in {"OOS_RESERVED", "OOS_UNTOUCHED", "CONSUMED_FORBIDDEN"}:
        # Catalog-only records for OOS/consumed must never mark consumable fields true.
        pass

    retrieval = retrieval_timestamp or utc_now_iso()
    lineage = build_lineage(
        source_id=source_id,
        source_kind=source_kind,
        source_path=source_path,
        source_checksum=content_checksum,
        availability_ms=availability_ms,
        retrieval_timestamp=retrieval,
        partition_id=partition_id,
        partition_category=partition_category,
    )
    record_id = sha_obj(
        {
            "source_id": source_id,
            "content_checksum": content_checksum,
            "partition_id": partition_id,
            "availability_ms": availability_ms,
        }
    )[:32]

    record: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "source_id": source_id,
        "source_kind": source_kind,
        "source_path": source_path,
        "source_timestamp": source_timestamp,
        "availability_timestamp": ms_to_iso(availability_ms),
        "availability_ms": availability_ms,
        "retrieval_timestamp": retrieval,
        "lineage": lineage,
        "content_checksum": content_checksum,
        "availability_state": availability_state,
        "staleness_state": _staleness_state(
            availability_ms=availability_ms,
            retrieval_timestamp=retrieval,
            max_age_ms=None,
        ),
        "missing_state": missing_state,
        "partition_id": partition_id,
        "partition_category": partition_category,
        "oos_consumed": False,
        "invented_history": False,
        "notes": notes,
        "payload_summary": payload_summary or {},
        **HARD_BAN_FLAGS,
    }
    # Strip duplicate keys from HARD_BAN_FLAGS already set explicitly
    record["oos_consumed"] = False
    record["invented_history"] = False
    record["record_hash"] = sha_obj({k: v for k, v in record.items() if k != "record_hash"})
    return record


def verify_record(record: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in REQUIRED_RECORD_KEYS if k not in record]
    if missing:
        return {"ok": False, "status": "MISSING_KEYS", "missing": missing}
    if record.get("invented_history") is True:
        return {"ok": False, "status": "INVENTED_HISTORY_FORBIDDEN"}
    if record.get("oos_consumed") is True:
        return {"ok": False, "status": "OOS_CONSUMED_FORBIDDEN"}
    if record.get("availability_state") not in AVAILABILITY_STATES:
        return {"ok": False, "status": "BAD_AVAILABILITY_STATE"}
    expected = sha_obj({k: v for k, v in record.items() if k != "record_hash"})
    if expected != record.get("record_hash"):
        return {"ok": False, "status": "RECORD_HASH_MISMATCH", "expected": expected}
    cat = str(record.get("partition_category"))
    if cat in {"OOS_RESERVED", "OOS_UNTOUCHED", "CONSUMED_FORBIDDEN"}:
        # Catalog allowed, but must not claim development consumption.
        if record.get("payload_summary", {}).get("loaded_for_development") is True:
            return {"ok": False, "status": "OOS_LOADED_FOR_DEVELOPMENT"}
    return {"ok": True, "status": "PASS", "record_id": record["record_id"]}
