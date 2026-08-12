"""Checksum and UTC helpers for V17-B Bronze lake."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.nexus_bronze_immutable_raw_lake.hard_bans import HardBanViolation, refuse_non_utc

# Strict UTC ISO-8601 ending in Z (no numeric offset, no naive).
_UTC_Z_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$"
)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_obj(obj: Any) -> str:
    return sha_bytes(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode(
            "utf-8"
        )
    )


def canonical_payload_bytes(payload: Any) -> bytes:
    """Canonical encoding for content_hash — raw JSON bytes, sorted keys."""
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_hash_of(payload: Any) -> str:
    return sha_bytes(canonical_payload_bytes(payload))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def assert_utc_z(ts: str, *, field: str) -> str:
    if not isinstance(ts, str) or not _UTC_Z_RE.match(ts):
        refuse_non_utc()
        raise HardBanViolation(f"no_non_utc_timestamps:{field}")
    # Round-trip parse to reject impossible calendar values.
    try:
        datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        # Allow fractional seconds
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HardBanViolation(f"no_non_utc_timestamps:{field}:parse") from exc
    return ts


def partition_key(*, source_id: str, symbol_original: str, exchange_timestamp: str) -> str:
    day = exchange_timestamp[:10]
    return f"{source_id}|{symbol_original}|{day}"


def partition_hash_of(*, source_id: str, symbol_original: str, exchange_timestamp: str) -> str:
    return sha_obj(
        {
            "source_id": source_id,
            "symbol_original": symbol_original,
            "day_utc": exchange_timestamp[:10],
        }
    )
