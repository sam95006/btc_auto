"""Immutable identity helpers for Decision Memory Graph nodes/edges."""
from __future__ import annotations

from typing import Any

from backend.nexus_decision_memory_graph.hashing import sha256_hex


def make_immutable_id(
    *,
    kind: str,
    material: dict[str, Any],
    namespace: str = "dmg",
) -> str:
    """Derive a stable immutable ID from kind + canonical material.

    IDs are content-addressed and must not be reassigned after seal.
    """
    digest = sha256_hex({"kind": kind, "material": material, "ns": namespace})
    return f"{namespace}_{kind.lower()}_{digest[:24]}"


def assert_id_immutable(existing_id: str, candidate_id: str) -> None:
    if existing_id != candidate_id:
        raise ValueError(f"immutable_id_collision:{existing_id}->{candidate_id}")
