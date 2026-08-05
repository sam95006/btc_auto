"""Core Decision Memory Graph — seal nodes/edges, PIT lookup, similarity."""
from __future__ import annotations

from typing import Any

from backend.nexus_decision_memory_graph.constants import (
    DEFAULT_CODE_VERSION,
    DEFAULT_MODEL_VERSION,
    DEFAULT_POLICY_VERSION,
    EDGE_SCHEMA,
    GRAPH_SCHEMA,
    NODE_SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_decision_memory_graph.failsafe import unavailable_response
from backend.nexus_decision_memory_graph.hashing import edge_lineage_hash, lineage_hash
from backend.nexus_decision_memory_graph.ids import make_immutable_id
from backend.nexus_decision_memory_graph.public_projection import (
    project_node_public,
    project_subgraph_public,
)
from backend.nexus_decision_memory_graph.schema import SchemaError, validate_edge_record, validate_node_record
from backend.nexus_decision_memory_graph.secrets import assert_no_secrets
from backend.nexus_decision_memory_graph.similarity import (
    SimilarityQueryError,
    build_similarity_query,
    score_similarity,
    validate_similarity_query,
)
from backend.nexus_decision_memory_graph.storage import (
    GraphStorageProtocol,
    InMemoryGraphStorage,
    StorageError,
)


class DecisionMemoryGraphError(RuntimeError):
    """Fail-closed graph operation error."""


class DecisionMemoryGraph:
    """Versioned, PIT-bound, immutable decision memory graph.

    Storage is swappable via GraphStorageProtocol. Default is in-memory —
    no external graph database is required for tests.
    """

    def __init__(self, storage: GraphStorageProtocol | None = None) -> None:
        self.storage: GraphStorageProtocol = storage or InMemoryGraphStorage()
        self.schema = GRAPH_SCHEMA
        self.schema_version = SCHEMA_VERSION

    def _default_version_pins(self, pins: dict[str, str] | None = None) -> dict[str, str]:
        base = {
            "code_version": DEFAULT_CODE_VERSION,
            "model_version": DEFAULT_MODEL_VERSION,
            "policy_version": DEFAULT_POLICY_VERSION,
        }
        if pins:
            base.update({str(k): str(v) for k, v in pins.items()})
        return base

    def seal_node(
        self,
        *,
        kind: str,
        as_of_ms: int,
        payload: dict[str, Any] | None = None,
        parent_lineage_hashes: list[str] | None = None,
        version_pins: dict[str, str] | None = None,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.storage.is_available():
            return unavailable_response(operation="seal_node")
        body = dict(payload or {})
        assert_no_secrets(body)
        pins = self._default_version_pins(version_pins)
        lh = lineage_hash(
            node_kind=kind,
            payload=body,
            as_of_ms=as_of_ms,
            parent_lineage_hashes=parent_lineage_hashes,
            version_pins=pins,
        )
        material = {
            "as_of_ms": int(as_of_ms),
            "kind": kind,
            "lineage_hash": lh,
            "payload": body,
            "version_pins": pins,
        }
        nid = node_id or make_immutable_id(kind=kind, material=material)
        node = {
            "schema": NODE_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "node_id": nid,
            "kind": kind,
            "as_of_ms": int(as_of_ms),
            "payload": body,
            "lineage_hash": lh,
            "parent_lineage_hashes": sorted(parent_lineage_hashes or []),
            "pit_bound": True,
            "immutable": True,
            "version_pins": pins,
        }
        validate_node_record(node)
        try:
            self.storage.put_node(node)
        except StorageError as exc:
            if "unavailable" in str(exc):
                return unavailable_response(operation="seal_node", reason=str(exc))
            raise DecisionMemoryGraphError(str(exc)) from exc
        return dict(node)

    def seal_edge(
        self,
        *,
        kind: str,
        from_id: str,
        to_id: str,
        as_of_ms: int,
        attrs: dict[str, Any] | None = None,
        edge_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.storage.is_available():
            return unavailable_response(operation="seal_edge")
        body = dict(attrs or {})
        assert_no_secrets(body)
        if self.storage.get_node(from_id) is None:
            raise DecisionMemoryGraphError(f"edge_from_missing:{from_id}")
        if self.storage.get_node(to_id) is None:
            raise DecisionMemoryGraphError(f"edge_to_missing:{to_id}")
        lh = edge_lineage_hash(
            edge_kind=kind,
            from_id=from_id,
            to_id=to_id,
            as_of_ms=as_of_ms,
            attrs=body,
        )
        material = {
            "as_of_ms": int(as_of_ms),
            "attrs": body,
            "from_id": from_id,
            "kind": kind,
            "lineage_hash": lh,
            "to_id": to_id,
        }
        eid = edge_id or make_immutable_id(kind=kind, material=material, namespace="dmg_e")
        edge = {
            "schema": EDGE_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "edge_id": eid,
            "kind": kind,
            "from_id": from_id,
            "to_id": to_id,
            "as_of_ms": int(as_of_ms),
            "attrs": body,
            "lineage_hash": lh,
            "immutable": True,
            "pit_bound": True,
        }
        validate_edge_record(edge)
        try:
            self.storage.put_edge(edge)
        except StorageError as exc:
            if "unavailable" in str(exc):
                return unavailable_response(operation="seal_edge", reason=str(exc))
            raise DecisionMemoryGraphError(str(exc)) from exc
        return dict(edge)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        if not self.storage.is_available():
            return unavailable_response(operation="get_node")  # type: ignore[return-value]
        try:
            return self.storage.get_node(node_id)
        except StorageError as exc:
            return unavailable_response(operation="get_node", reason=str(exc))  # type: ignore[return-value]

    def pit_lookup(
        self,
        *,
        as_of_ms: int,
        kinds: list[str] | None = None,
    ) -> dict[str, Any]:
        """Point-in-time subgraph: only nodes/edges with as_of_ms <= query time."""
        if not self.storage.is_available():
            return unavailable_response(operation="pit_lookup")
        try:
            nodes = self.storage.nodes_as_of(as_of_ms)
            edges = self.storage.edges_as_of(as_of_ms)
        except StorageError as exc:
            return unavailable_response(operation="pit_lookup", reason=str(exc))

        # Reject future leakage: storage contract already filters, assert defensively.
        for n in nodes:
            if int(n["as_of_ms"]) > int(as_of_ms):
                raise DecisionMemoryGraphError("future_leakage_in_pit_nodes")
        for e in edges:
            if int(e["as_of_ms"]) > int(as_of_ms):
                raise DecisionMemoryGraphError("future_leakage_in_pit_edges")

        if kinds is not None:
            allow = set(kinds)
            nodes = [n for n in nodes if n["kind"] in allow]
            node_ids = {n["node_id"] for n in nodes}
            edges = [e for e in edges if e["from_id"] in node_ids and e["to_id"] in node_ids]

        return {
            "ok": True,
            "as_of_ms": int(as_of_ms),
            "pit_bound": True,
            "future_leakage": False,
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "schema": GRAPH_SCHEMA,
            "schema_version": SCHEMA_VERSION,
        }

    def similarity_query(
        self,
        *,
        query_id: str,
        as_of_ms: int,
        anchor_node_id: str,
        dimensions: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if not self.storage.is_available():
            return unavailable_response(operation="similarity_query")
        query = build_similarity_query(
            query_id=query_id,
            as_of_ms=as_of_ms,
            anchor_node_id=anchor_node_id,
            dimensions=dimensions,
            limit=limit,
        )
        validate_similarity_query(query)
        pit = self.pit_lookup(as_of_ms=as_of_ms)
        if not pit.get("ok"):
            return pit
        anchor = next((n for n in pit["nodes"] if n["node_id"] == anchor_node_id), None)
        if anchor is None:
            # Anchor may exist but be after as_of — PIT miss is not an invention.
            return {
                "ok": True,
                "query": query,
                "results": [],
                "anchor_found": False,
                "pit_bound": True,
            }
        scored: list[dict[str, Any]] = []
        for cand in pit["nodes"]:
            if cand["node_id"] == anchor_node_id:
                continue
            if cand["kind"] != anchor["kind"]:
                continue
            s = score_similarity(anchor, cand, query["dimensions"])
            scored.append(
                {
                    "node_id": cand["node_id"],
                    "kind": cand["kind"],
                    "score": s,
                    "lineage_hash": cand["lineage_hash"],
                    "as_of_ms": cand["as_of_ms"],
                }
            )
        scored.sort(key=lambda r: (-r["score"], r["node_id"]))
        return {
            "ok": True,
            "query": query,
            "results": scored[: int(limit)],
            "anchor_found": True,
            "pit_bound": True,
            "ranking_claim": False,
            "profitability_claim": False,
        }

    def public_view(self, *, as_of_ms: int) -> dict[str, Any]:
        pit = self.pit_lookup(as_of_ms=as_of_ms)
        if not pit.get("ok"):
            return pit
        return project_subgraph_public(pit["nodes"], pit["edges"])

    def public_node(self, node_id: str) -> dict[str, Any] | None:
        node = self.get_node(node_id)
        if isinstance(node, dict) and node.get("mode"):
            # Fail-safe envelope — project as unavailable public stub, never raw private.
            return project_node_public(node)
        return project_node_public(node)

    # Explicit mutation surface bans
    def update_node(self, *_a: Any, **_k: Any) -> None:
        raise DecisionMemoryGraphError("mutation_forbidden_immutable_graph")

    def delete_node(self, *_a: Any, **_k: Any) -> None:
        raise DecisionMemoryGraphError("deletion_forbidden_immutable_graph")

    def rewrite_lineage(self, *_a: Any, **_k: Any) -> None:
        raise DecisionMemoryGraphError("lineage_rewrite_forbidden")
