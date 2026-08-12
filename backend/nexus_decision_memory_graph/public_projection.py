"""Public-safe projection — never leak private fields to public apps."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_decision_memory_graph.constants import (
    PRIVATE_FIELD_NAMES,
    PUBLIC_PROJECTION_SCHEMA,
    PUBLIC_SAFE_PAYLOAD_KEYS,
    SCHEMA_VERSION,
)
from backend.nexus_decision_memory_graph.hard_bans import HardBanViolation


def _strip_private_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in PRIVATE_FIELD_NAMES or any(
                tok in lk for tok in ("secret", "password", "private_key", "api_key", "token")
            ):
                continue
            out[str(k)] = _strip_private_keys(v)
        return out
    if isinstance(obj, list):
        return [_strip_private_keys(x) for x in obj]
    return obj


def project_node_public(node: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project a sealed node to a public-safe DTO.

    Whitelists payload keys and strips private field names. Raw private
    memory blobs and proprietary thresholds are never emitted.
    """
    if node is None:
        return None
    # Never project fail-safe / unavailable envelopes as public nodes.
    if node.get("mode") == "GRAPH_UNAVAILABLE_FAIL_SAFE":
        return {
            "schema": PUBLIC_PROJECTION_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "unavailable": True,
            "data_class": "PUBLIC_SAFE",
            "raw_memory_graph": False,
            "private_fields_included": False,
            "payload": {},
        }
    payload = node.get("payload") if isinstance(node.get("payload"), dict) else {}
    safe_payload = {
        k: deepcopy(v)
        for k, v in payload.items()
        if str(k) in PUBLIC_SAFE_PAYLOAD_KEYS and str(k).lower() not in PRIVATE_FIELD_NAMES
    }
    safe_payload = _strip_private_keys(safe_payload)
    out = {
        "schema": PUBLIC_PROJECTION_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "node_id": node.get("node_id"),
        "kind": node.get("kind"),
        "as_of_ms": node.get("as_of_ms"),
        "lineage_hash": node.get("lineage_hash"),
        "payload": safe_payload,
        "data_class": "PUBLIC_SAFE",
        "raw_memory_graph": False,
        "private_fields_included": False,
    }
    assert_no_private_leak(out)
    return out


def project_subgraph_public(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    public_nodes = [project_node_public(n) for n in nodes]
    public_edges = [
        {
            "schema": PUBLIC_PROJECTION_SCHEMA,
            "edge_id": e.get("edge_id"),
            "kind": e.get("kind"),
            "from_id": e.get("from_id"),
            "to_id": e.get("to_id"),
            "as_of_ms": e.get("as_of_ms"),
            "attrs": {},  # never project private edge attrs
        }
        for e in edges
    ]
    blob = {
        "schema": PUBLIC_PROJECTION_SCHEMA,
        "nodes": public_nodes,
        "edges": public_edges,
        "raw_memory_graph": False,
    }
    assert_no_private_leak(blob)
    return blob


def assert_no_private_leak(projection: Any) -> None:
    """Fail-closed if any private field name survives public projection."""

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                lk = str(k).lower()
                if lk in PRIVATE_FIELD_NAMES:
                    raise HardBanViolation(f"no_private_field_leak_to_public:{path}.{k}")
                if lk in {"raw_memory_blob", "raw_memory_graph"} and v not in (False, None, 0):
                    raise HardBanViolation(f"no_private_field_leak_to_public:raw:{path}.{k}")
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk(item, f"{path}[{i}]")

    walk(projection)
