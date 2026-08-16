"""Versioned event contract — excludes execution commands."""
from __future__ import annotations

from typing import Any

EVENT_CONTRACT_VERSION = "v18_3_3_event_contract_v1"

EVENT_TYPES = (
    "market.observation",
    "opportunity.candidate",
    "decision.ai",
    "decision.risk",
    "shadow.position.open",
    "shadow.position.close",
    "alert.runtime",
    "runtime.health",
)

EXCLUDED_EVENT_TYPES = frozenset(
    {
        "execution.order.submit",
        "execution.order.cancel",
        "demo.order.submit",
        "mainnet.order.submit",
        "policy.mutation.apply",
    }
)


def event_envelope(
    *,
    event_id: str,
    event_type: str,
    occurred_at: str,
    sequence: int,
    payload: dict[str, Any],
    reconnect_cursor: str | None = None,
) -> dict[str, Any]:
    if event_type in EXCLUDED_EVENT_TYPES:
        raise ValueError(f"forbidden_event_type:{event_type}")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown_event_type:{event_type}")
    return {
        "schema": EVENT_CONTRACT_VERSION,
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "sequence": sequence,
        "reconnect_cursor": reconnect_cursor or f"{sequence}:{event_id}",
        "dedupe_key": event_id,
        "payload": payload,
    }


def contract_snapshot() -> dict[str, Any]:
    return {
        "schema": EVENT_CONTRACT_VERSION,
        "event_types": list(EVENT_TYPES),
        "excluded_event_types": sorted(EXCLUDED_EVENT_TYPES),
        "dedupe_semantics": "event_id_primary_reconnect_cursor_secondary",
        "execution_commands_mapped": False,
    }


def validate_contract() -> dict[str, Any]:
    overlap = set(EVENT_TYPES) & EXCLUDED_EVENT_TYPES
    return {
        "ok": not overlap,
        "errors": [f"overlap:{x}" for x in sorted(overlap)],
        "contract": contract_snapshot(),
    }
