"""Canonical hashing helpers for experiment identity and seals."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(obj: Any) -> str:
    if isinstance(obj, (bytes, bytearray)):
        return hashlib.sha256(obj).hexdigest()
    if isinstance(obj, str):
        return hashlib.sha256(obj.encode("utf-8")).hexdigest()
    return hashlib.sha256(canonical_dumps(obj).encode("utf-8")).hexdigest()


def checksum_parameters(parameters: dict[str, Any] | None) -> str:
    return sha256_hex(parameters or {})


def checksum_universe(members: list[str] | tuple[str, ...] | None, *, as_of_ms: int | None = None) -> str:
    payload = {
        "members": sorted({str(m) for m in (members or [])}),
        "as_of_ms": as_of_ms,
    }
    return sha256_hex(payload)


def checksum_code(blob: str | bytes | dict[str, Any]) -> str:
    return sha256_hex(blob)


def checksum_lineage(lineage: dict[str, Any]) -> str:
    return sha256_hex(lineage)
