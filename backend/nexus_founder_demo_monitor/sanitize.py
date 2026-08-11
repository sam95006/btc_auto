"""Sanitize founder demo-monitor payloads — strip secrets / order ids."""
from __future__ import annotations

from typing import Any

from backend.nexus_founder_demo_monitor.constants import FORBIDDEN_PAYLOAD_KEYS


def assert_no_forbidden_keys(payload: dict[str, Any]) -> list[str]:
    hits: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}" if path else str(k)
                if k in FORBIDDEN_PAYLOAD_KEYS:
                    hits.append(p)
                walk(v, p)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(payload, "")
    return hits


def strip_forbidden_keys(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            k: strip_forbidden_keys(v)
            for k, v in node.items()
            if k not in FORBIDDEN_PAYLOAD_KEYS
        }
    if isinstance(node, list):
        return [strip_forbidden_keys(x) for x in node]
    return node
