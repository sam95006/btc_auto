"""Routing policy for V18-E AI Gateway."""
from __future__ import annotations

from typing import Any

from backend.nexus_ai_gateway_tool_sandbox.constants import (
    ROLE_PROVIDER_CHAIN,
    ROUTE_ROLES,
)


def classify_role(payload: dict[str, Any] | None = None, *, explicit_role: str | None = None) -> str:
    """
    Routing:
      simple → SIMPLE (deterministic / low-cost)
      candidate interpretation → CANDIDATE_INTERPRETATION (primary)
      major contradictions → MAJOR_CONTRADICTION_CRITIC
    """
    if explicit_role:
        role = explicit_role.strip().upper()
        if role in ROUTE_ROLES:
            return role
        aliases = {
            "SIMPLE_TASK": "SIMPLE",
            "LOW_COST": "SIMPLE",
            "CANDIDATE": "CANDIDATE_INTERPRETATION",
            "PRIMARY": "CANDIDATE_INTERPRETATION",
            "CRITIC": "MAJOR_CONTRADICTION_CRITIC",
            "CONTRADICTION": "MAJOR_CONTRADICTION_CRITIC",
        }
        if role in aliases:
            return aliases[role]

    data = payload or {}
    if data.get("major_contradiction") or data.get("requires_critic"):
        return "MAJOR_CONTRADICTION_CRITIC"
    if data.get("simple") or data.get("task_class") == "simple":
        return "SIMPLE"
    if data.get("candidate") or data.get("task_class") == "candidate_interpretation":
        return "CANDIDATE_INTERPRETATION"
    # Default: treat as candidate interpretation (primary path).
    return "CANDIDATE_INTERPRETATION"


def provider_chain_for_role(role: str) -> tuple[str, ...]:
    return ROLE_PROVIDER_CHAIN.get(role, ROLE_PROVIDER_CHAIN["CANDIDATE_INTERPRETATION"])
