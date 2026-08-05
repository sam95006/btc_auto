"""Lineage builders for V15-A PIT development data records."""
from __future__ import annotations

from typing import Any

from backend.nexus_dev_data_foundation.constants import LINEAGE_SCHEMA, PROGRAM_ID
from backend.nexus_dev_data_foundation.hashing import sha_obj


def build_lineage(
    *,
    source_id: str,
    source_kind: str,
    source_path: str | None,
    source_checksum: str,
    availability_ms: int | None,
    retrieval_timestamp: str,
    partition_id: str | None,
    partition_category: str,
    parent_lineage_id: str | None = None,
    code_version: str = "v15_a_dev_data_foundation_1",
) -> dict[str, Any]:
    core = {
        "source_id": source_id,
        "source_kind": source_kind,
        "source_checksum": source_checksum,
        "availability_ms": availability_ms,
        "partition_id": partition_id,
        "partition_category": partition_category,
        "code_version": code_version,
        "program_id": PROGRAM_ID,
    }
    lineage_id = sha_obj(core)[:32]
    return {
        "schema": LINEAGE_SCHEMA,
        "lineage_id": lineage_id,
        "parent_lineage_id": parent_lineage_id,
        "program_id": PROGRAM_ID,
        "source_id": source_id,
        "source_kind": source_kind,
        "source_path": source_path,
        "source_checksum": source_checksum,
        "availability_ms": availability_ms,
        "retrieval_timestamp": retrieval_timestamp,
        "partition_id": partition_id,
        "partition_category": partition_category,
        "code_version": code_version,
        "pit_guarantees": {
            "never_uses_today_for_past": True,
            "never_invents_missing_history": True,
            "oos_not_consumed": True,
            "future_observation_rejected": True,
        },
        "exchange_write": False,
        "demo": False,
        "pr26_merged": False,
        "pr27_merged": False,
        "lineage_digest": sha_obj({**core, "lineage_id": lineage_id}),
    }
