"""Checksum / UTC helpers for V18-B."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.nexus_incremental_backfill_live_ingest.hard_bans import (
    HardBanViolation,
    refuse_future_timestamp_accept,
)

_UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_obj(obj: Any) -> str:
    return sha_bytes(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode(
            "utf-8"
        )
    )


def content_hash_of(payload: Any) -> str:
    if isinstance(payload, (bytes, bytearray)):
        return sha_bytes(bytes(payload))
    if isinstance(payload, str):
        return sha_bytes(payload.encode("utf-8"))
    return sha_obj(payload)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def assert_utc_z(ts: str, *, field: str) -> str:
    if not isinstance(ts, str) or not _UTC_Z_RE.match(ts):
        raise HardBanViolation(f"no_non_utc_timestamps:{field}")
    try:
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HardBanViolation(f"no_non_utc_timestamps:{field}:parse") from exc
    return ts


def parse_utc_z_ms(ts: str) -> int:
    assert_utc_z(ts, field="timestamp")
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def reject_future_timestamp(ts: str, *, now_ms: int | None = None, skew_ms: int = 60_000) -> str:
    """Refuse exchange timestamps more than skew_ms in the future."""
    assert_utc_z(ts, field="exchange_timestamp")
    ts_ms = parse_utc_z_ms(ts)
    ref = now_ms if now_ms is not None else utc_now_ms()
    if ts_ms > ref + int(skew_ms):
        refuse_future_timestamp_accept()
    return ts


def day_partition(ts: str) -> str:
    assert_utc_z(ts, field="exchange_timestamp")
    return ts[:10]
