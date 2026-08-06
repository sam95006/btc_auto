"""Bronze record construction and validation — append-only raw envelope."""
from __future__ import annotations

from typing import Any

from backend.nexus_bronze_immutable_raw_lake.constants import (
    ALLOWED_COMPRESSIONS,
    ALLOWED_INGEST_CLASSIFICATIONS,
    BRONZE_REQUIRED_FIELDS,
    CLASSIFICATION_FULL_HISTORY,
    COMPRESSION_NONE,
    DEFAULT_LICENSE_REFERENCE,
    SCHEMA_RECORD,
    SCHEMA_VERSION,
)
from backend.nexus_bronze_immutable_raw_lake.hard_bans import (
    HardBanViolation,
    refuse_15y_history_claim,
    refuse_ai_mutate_raw_payload,
    refuse_full_history_ingest,
)
from backend.nexus_bronze_immutable_raw_lake.hashing import (
    assert_utc_z,
    content_hash_of,
    partition_hash_of,
    utc_now_iso,
)
from backend.nexus_bronze_immutable_raw_lake.lineage import build_lineage


class BronzeRecordError(ValueError):
    pass


def build_bronze_record(
    *,
    exchange_timestamp: str,
    received_timestamp: str,
    source_id: str,
    symbol_original: str,
    payload: Any,
    classification: str,
    license_reference: str = DEFAULT_LICENSE_REFERENCE,
    compression: str = COMPRESSION_NONE,
    ingested_timestamp: str | None = None,
    schema_version: str = SCHEMA_VERSION,
) -> dict[str, Any]:
    if classification == CLASSIFICATION_FULL_HISTORY:
        refuse_full_history_ingest()
    if classification not in ALLOWED_INGEST_CLASSIFICATIONS:
        raise BronzeRecordError(f"classification_refused:{classification}")
    if "15y" in str(classification).lower() or "15 year" in str(payload).lower():
        refuse_15y_history_claim()
    if compression not in ALLOWED_COMPRESSIONS:
        raise BronzeRecordError(f"compression_unsupported:{compression}")

    ex_ts = assert_utc_z(exchange_timestamp, field="exchange_timestamp")
    rx_ts = assert_utc_z(received_timestamp, field="received_timestamp")
    ing_ts = assert_utc_z(ingested_timestamp or utc_now_iso(), field="ingested_timestamp")

    c_hash = content_hash_of(payload)
    p_hash = partition_hash_of(
        source_id=source_id,
        symbol_original=symbol_original,
        exchange_timestamp=ex_ts,
    )
    lineage = build_lineage(
        source_id=source_id,
        content_hash=c_hash,
        partition_hash=p_hash,
        classification=classification,
        license_reference=license_reference,
    )

    record: dict[str, Any] = {
        "schema": SCHEMA_RECORD,
        "schema_version": schema_version,
        "exchange_timestamp": ex_ts,
        "received_timestamp": rx_ts,
        "ingested_timestamp": ing_ts,
        "source_id": source_id,
        "symbol_original": symbol_original,
        "payload": payload,
        "content_hash": c_hash,
        "partition_hash": p_hash,
        "compression": compression,
        "license_reference": license_reference,
        "classification": classification,
        "lineage": lineage,
        "ai_mutable": False,
        "append_only": True,
        "record_id": c_hash[:32],
    }
    verify_bronze_record(record)
    return record


def verify_bronze_record(record: dict[str, Any]) -> None:
    missing = [f for f in BRONZE_REQUIRED_FIELDS if f not in record]
    if missing:
        raise BronzeRecordError(f"missing_fields:{','.join(missing)}")
    for field in ("exchange_timestamp", "received_timestamp", "ingested_timestamp"):
        assert_utc_z(record[field], field=field)
    expected = content_hash_of(record["payload"])
    if record["content_hash"] != expected:
        raise BronzeRecordError("content_hash_mismatch")
    expected_p = partition_hash_of(
        source_id=record["source_id"],
        symbol_original=record["symbol_original"],
        exchange_timestamp=record["exchange_timestamp"],
    )
    if record["partition_hash"] != expected_p:
        raise BronzeRecordError("partition_hash_mismatch")
    if record.get("ai_mutable") is True:
        refuse_ai_mutate_raw_payload()
    if record.get("compression") not in ALLOWED_COMPRESSIONS:
        raise BronzeRecordError("compression_invalid")


def attempt_ai_mutate_payload(record: dict[str, Any], new_payload: Any) -> dict[str, Any]:
    """AI mutation of raw bronze payload is hard-banned."""
    _ = (record, new_payload)
    refuse_ai_mutate_raw_payload()
    raise HardBanViolation("no_ai_mutate_raw_payload")
