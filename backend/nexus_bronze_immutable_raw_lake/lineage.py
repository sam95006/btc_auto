"""Lineage builders for V17-B Bronze records."""
from __future__ import annotations

from typing import Any

from backend.nexus_bronze_immutable_raw_lake.constants import PROGRAM_ID, SCHEMA_LINEAGE
from backend.nexus_bronze_immutable_raw_lake.hashing import sha_obj, utc_now_iso


def build_lineage(
    *,
    source_id: str,
    content_hash: str,
    partition_hash: str,
    classification: str,
    license_reference: str,
    parent_lineage_id: str | None = None,
    code_version: str = "v17_b_bronze_immutable_raw_lake_1",
) -> dict[str, Any]:
    core = {
        "source_id": source_id,
        "content_hash": content_hash,
        "partition_hash": partition_hash,
        "classification": classification,
        "license_reference": license_reference,
        "code_version": code_version,
        "program_id": PROGRAM_ID,
    }
    lineage_id = sha_obj(core)[:32]
    return {
        "schema": SCHEMA_LINEAGE,
        "lineage_id": lineage_id,
        "parent_lineage_id": parent_lineage_id,
        "program_id": PROGRAM_ID,
        "source_id": source_id,
        "content_hash": content_hash,
        "partition_hash": partition_hash,
        "classification": classification,
        "license_reference": license_reference,
        "code_version": code_version,
        "built_at": utc_now_iso(),
        "guarantees": {
            "append_only": True,
            "no_historical_rewrite": True,
            "raw_payload_ai_immutable": True,
            "utc_only": True,
            "checksum_enforced": True,
        },
        "exchange_write": False,
        "demo": False,
        "pr26_merged": False,
        "pr27_merged": False,
        "lineage_digest": sha_obj({**core, "lineage_id": lineage_id}),
    }
