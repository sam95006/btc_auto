"""Fail-safe behavior when Decision Memory Graph is unavailable."""
from __future__ import annotations

from typing import Any

from backend.nexus_decision_memory_graph.constants import UNAVAILABLE_MODE


def unavailable_response(*, operation: str, reason: str = "graph_unavailable") -> dict[str, Any]:
    """Safe degraded response — never invent nodes/edges or fail open to trade."""
    return {
        "ok": False,
        "mode": UNAVAILABLE_MODE,
        "operation": str(operation),
        "reason": str(reason),
        "nodes": [],
        "edges": [],
        "results": [],
        "fail_open": False,
        "trading_allowed": False,
        "fabricated": False,
    }


def is_fail_safe(payload: dict[str, Any]) -> bool:
    return (
        payload.get("mode") == UNAVAILABLE_MODE
        and payload.get("fail_open") is False
        and payload.get("trading_allowed") is False
        and payload.get("fabricated") is False
    )
