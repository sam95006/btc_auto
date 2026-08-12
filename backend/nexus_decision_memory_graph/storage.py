"""Swappable storage abstraction for Decision Memory Graph.

Tests must run without any external graph database. InMemoryGraphStorage is the
default; alternate backends implement GraphStorageProtocol.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol, runtime_checkable


class StorageError(RuntimeError):
    """Fail-closed storage error."""


@runtime_checkable
class GraphStorageProtocol(Protocol):
    """Minimal swappable storage contract — no external DB required."""

    def put_node(self, node: dict[str, Any]) -> None: ...

    def get_node(self, node_id: str) -> dict[str, Any] | None: ...

    def put_edge(self, edge: dict[str, Any]) -> None: ...

    def get_edge(self, edge_id: str) -> dict[str, Any] | None: ...

    def list_node_ids(self) -> list[str]: ...

    def list_edge_ids(self) -> list[str]: ...

    def nodes_as_of(self, as_of_ms: int) -> list[dict[str, Any]]: ...

    def edges_as_of(self, as_of_ms: int) -> list[dict[str, Any]]: ...

    def mark_unavailable(self) -> None: ...

    def is_available(self) -> bool: ...


class InMemoryGraphStorage:
    """Process-local append-only graph store for tests and local development."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: dict[str, dict[str, Any]] = {}
        self._available = True

    def put_node(self, node: dict[str, Any]) -> None:
        if not self._available:
            raise StorageError("graph_unavailable")
        nid = str(node["node_id"])
        if nid in self._nodes:
            raise StorageError(f"node_immutable_duplicate:{nid}")
        self._nodes[nid] = deepcopy(node)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        if not self._available:
            raise StorageError("graph_unavailable")
        node = self._nodes.get(node_id)
        return deepcopy(node) if node else None

    def put_edge(self, edge: dict[str, Any]) -> None:
        if not self._available:
            raise StorageError("graph_unavailable")
        eid = str(edge["edge_id"])
        if eid in self._edges:
            raise StorageError(f"edge_immutable_duplicate:{eid}")
        self._edges[eid] = deepcopy(edge)

    def get_edge(self, edge_id: str) -> dict[str, Any] | None:
        if not self._available:
            raise StorageError("graph_unavailable")
        edge = self._edges.get(edge_id)
        return deepcopy(edge) if edge else None

    def list_node_ids(self) -> list[str]:
        if not self._available:
            raise StorageError("graph_unavailable")
        return list(self._nodes.keys())

    def list_edge_ids(self) -> list[str]:
        if not self._available:
            raise StorageError("graph_unavailable")
        return list(self._edges.keys())

    def nodes_as_of(self, as_of_ms: int) -> list[dict[str, Any]]:
        if not self._available:
            raise StorageError("graph_unavailable")
        rows = [
            deepcopy(n)
            for n in self._nodes.values()
            if int(n["as_of_ms"]) <= int(as_of_ms)
        ]
        rows.sort(key=lambda n: (int(n["as_of_ms"]), str(n["node_id"])))
        return rows

    def edges_as_of(self, as_of_ms: int) -> list[dict[str, Any]]:
        if not self._available:
            raise StorageError("graph_unavailable")
        rows = [
            deepcopy(e)
            for e in self._edges.values()
            if int(e["as_of_ms"]) <= int(as_of_ms)
        ]
        rows.sort(key=lambda e: (int(e["as_of_ms"]), str(e["edge_id"])))
        return rows

    def mark_unavailable(self) -> None:
        self._available = False

    def is_available(self) -> bool:
        return self._available

    # Explicit mutation bans — immutability surface.
    def update_node(self, *_a: Any, **_k: Any) -> None:
        raise StorageError("mutation_forbidden_immutable_graph")

    def delete_node(self, *_a: Any, **_k: Any) -> None:
        raise StorageError("deletion_forbidden_immutable_graph")

    def update_edge(self, *_a: Any, **_k: Any) -> None:
        raise StorageError("mutation_forbidden_immutable_graph")

    def delete_edge(self, *_a: Any, **_k: Any) -> None:
        raise StorageError("deletion_forbidden_immutable_graph")
