"""Checksum, timestamp, and lineage helpers for PIT market discovery."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from backend.nexus_market_discovery.constants import LINEAGE_SCHEMA


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def universe_checksum(*, as_of_ms: int, eligible_symbols: list[str], rejected_symbols: list[str]) -> str:
    return sha_obj(
        {
            "as_of_ms": int(as_of_ms),
            "eligible": sorted(eligible_symbols),
            "rejected": sorted(rejected_symbols),
        }
    )


def build_lineage(
    *,
    as_of_ms: int,
    snapshot_id: str,
    snapshot_availability_ms: int,
    source_kind: str,
    source_path: str,
    source_checksum: str,
    retrieval_timestamp: str,
    code_version: str,
    thresholds_checksum: str,
    universe_checksum_value: str,
    parent_lineage_id: str | None = None,
) -> dict[str, Any]:
    lineage_id = sha_obj(
        {
            "as_of_ms": as_of_ms,
            "snapshot_id": snapshot_id,
            "source_checksum": source_checksum,
            "thresholds_checksum": thresholds_checksum,
            "universe_checksum": universe_checksum_value,
            "code_version": code_version,
        }
    )[:32]
    return {
        "schema": LINEAGE_SCHEMA,
        "lineage_id": lineage_id,
        "parent_lineage_id": parent_lineage_id,
        "as_of_ms": int(as_of_ms),
        "as_of_timestamp": ms_to_iso(as_of_ms),
        "availability_timestamp": ms_to_iso(snapshot_availability_ms),
        "availability_ms": int(snapshot_availability_ms),
        "retrieval_timestamp": retrieval_timestamp,
        "snapshot_id": snapshot_id,
        "source_kind": source_kind,
        "source_path": source_path,
        "source_checksum": source_checksum,
        "thresholds_checksum": thresholds_checksum,
        "universe_checksum": universe_checksum_value,
        "code_version": code_version,
        "pit_guarantees": {
            "uses_historical_snapshot_only": source_kind == "sanitized_fixture",
            "never_uses_today_for_past": True,
            "future_observation_rejected": True,
        },
        "exchange_write": False,
        "demo": False,
        "pr27_merged": False,
    }
