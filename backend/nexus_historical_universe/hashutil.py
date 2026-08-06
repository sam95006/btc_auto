"""Checksum and seal helpers for historical universe control."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def universe_checksum(
    *,
    as_of_ms: int,
    eligible_symbols: list[str],
    excluded_symbols: list[str],
) -> str:
    return sha_obj(
        {
            "as_of_ms": int(as_of_ms),
            "eligible": sorted(eligible_symbols),
            "excluded": sorted(excluded_symbols),
        }
    )
