"""Versioned schema validation for Decision Memory Graph nodes/edges."""
from __future__ import annotations

from typing import Any

from backend.nexus_decision_memory_graph.constants import (
    EDGE_KINDS,
    EDGE_SCHEMA,
    GRAPH_SCHEMA,
    NODE_KINDS,
    NODE_SCHEMA,
    SCHEMA_ID,
    SCHEMA_VERSION,
)


class SchemaError(ValueError):
    """Fail-closed schema violation."""


REQUIRED_NODE_KEYS: tuple[str, ...] = (
    "schema",
    "schema_version",
    "node_id",
    "kind",
    "as_of_ms",
    "payload",
    "lineage_hash",
    "pit_bound",
    "immutable",
    "version_pins",
)

REQUIRED_EDGE_KEYS: tuple[str, ...] = (
    "schema",
    "schema_version",
    "edge_id",
    "kind",
    "from_id",
    "to_id",
    "as_of_ms",
    "lineage_hash",
    "immutable",
)


def validate_node_record(node: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in REQUIRED_NODE_KEYS if k not in node]
    if missing:
        raise SchemaError(f"node_missing_keys:{missing}")
    if node.get("schema") != NODE_SCHEMA:
        raise SchemaError(f"node_schema_mismatch:{node.get('schema')}")
    if int(node.get("schema_version", -1)) != SCHEMA_VERSION:
        raise SchemaError(f"node_schema_version_mismatch:{node.get('schema_version')}")
    kind = str(node["kind"])
    if kind not in NODE_KINDS:
        raise SchemaError(f"unknown_node_kind:{kind}")
    if not node.get("immutable", False):
        raise SchemaError("node_must_be_immutable")
    if not node.get("pit_bound", False):
        raise SchemaError("node_must_be_pit_bound")
    if not isinstance(node.get("payload"), dict):
        raise SchemaError("node_payload_must_be_dict")
    if not isinstance(node.get("as_of_ms"), int) or node["as_of_ms"] < 0:
        raise SchemaError("node_as_of_ms_invalid")
    if not isinstance(node.get("lineage_hash"), str) or len(node["lineage_hash"]) != 64:
        raise SchemaError("node_lineage_hash_invalid")
    if not isinstance(node.get("version_pins"), dict):
        raise SchemaError("node_version_pins_must_be_dict")
    return {"ok": True, "node_id": node["node_id"], "kind": kind}


def validate_edge_record(edge: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in REQUIRED_EDGE_KEYS if k not in edge]
    if missing:
        raise SchemaError(f"edge_missing_keys:{missing}")
    if edge.get("schema") != EDGE_SCHEMA:
        raise SchemaError(f"edge_schema_mismatch:{edge.get('schema')}")
    if int(edge.get("schema_version", -1)) != SCHEMA_VERSION:
        raise SchemaError(f"edge_schema_version_mismatch:{edge.get('schema_version')}")
    kind = str(edge["kind"])
    if kind not in EDGE_KINDS:
        raise SchemaError(f"unknown_edge_kind:{kind}")
    if not edge.get("immutable", False):
        raise SchemaError("edge_must_be_immutable")
    if not isinstance(edge.get("as_of_ms"), int) or edge["as_of_ms"] < 0:
        raise SchemaError("edge_as_of_ms_invalid")
    if not isinstance(edge.get("lineage_hash"), str) or len(edge["lineage_hash"]) != 64:
        raise SchemaError("edge_lineage_hash_invalid")
    if not edge.get("from_id") or not edge.get("to_id"):
        raise SchemaError("edge_endpoints_required")
    return {"ok": True, "edge_id": edge["edge_id"], "kind": kind}


def schema_manifest() -> dict[str, Any]:
    return {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "graph_schema": GRAPH_SCHEMA,
        "node_schema": NODE_SCHEMA,
        "edge_schema": EDGE_SCHEMA,
        "node_kinds": list(NODE_KINDS),
        "edge_kinds": list(EDGE_KINDS),
        "versioned": True,
    }
