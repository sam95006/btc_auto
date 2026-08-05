"""Canonical hashing and lineage seals for V16-H Decision Memory Graph."""
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


def lineage_hash(
    *,
    node_kind: str,
    payload: dict[str, Any],
    as_of_ms: int,
    parent_lineage_hashes: list[str] | tuple[str, ...] | None = None,
    version_pins: dict[str, str] | None = None,
) -> str:
    """Deterministic lineage hash binding content, PIT clock, and parent seals."""
    material = {
        "as_of_ms": int(as_of_ms),
        "node_kind": str(node_kind),
        "parent_lineage_hashes": sorted(str(h) for h in (parent_lineage_hashes or [])),
        "payload": payload or {},
        "version_pins": version_pins or {},
    }
    return sha256_hex(material)


def edge_lineage_hash(
    *,
    edge_kind: str,
    from_id: str,
    to_id: str,
    as_of_ms: int,
    attrs: dict[str, Any] | None = None,
) -> str:
    material = {
        "as_of_ms": int(as_of_ms),
        "attrs": attrs or {},
        "edge_kind": str(edge_kind),
        "from_id": str(from_id),
        "to_id": str(to_id),
    }
    return sha256_hex(material)
