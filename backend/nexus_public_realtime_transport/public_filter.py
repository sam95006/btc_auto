"""Public-only event filtering for PUB2-E realtime reliability."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_realtime_transport.constants import (
    ALLOWED_EVENT_KINDS,
    FORBIDDEN_PRIVATE_TOPICS,
    PUBLIC_TOPIC_PREFIXES,
)
from backend.nexus_public_realtime_transport.hard_bans import HardBanViolation, refuse_private_topic
from backend.nexus_public_realtime_transport.sanitize import assert_no_forbidden_keys


def is_public_topic(topic: str) -> bool:
    norm = str(topic).strip().lower()
    if not norm:
        return False
    if norm in FORBIDDEN_PRIVATE_TOPICS:
        return False
    if norm.startswith("private.") or norm.startswith("founder."):
        return False
    if any(norm.startswith(p) for p in PUBLIC_TOPIC_PREFIXES):
        return True
    # Explicit public.decision.feed style without prefix match edge cases
    return norm.startswith("public")


def filter_public_event(
    *,
    kind: str,
    topic: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Admit only public-safe kinds/topics/payloads; raise HardBanViolation otherwise."""
    refuse_private_topic(topic)
    kind_n = str(kind).strip().lower()
    if kind_n not in ALLOWED_EVENT_KINDS:
        raise HardBanViolation(f"HARD BAN: disallowed event kind refused: {kind}")
    if not is_public_topic(topic):
        raise HardBanViolation(f"HARD BAN: non-public topic refused: {topic}")
    body = dict(payload or {})
    assert_no_forbidden_keys(body)
    return {
        "admitted": True,
        "kind": kind_n,
        "topic": str(topic).strip(),
        "payload": body,
        "public_only": True,
    }


def public_only_batch_filter(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Filter a mixed batch; private/forbidden rows are refused, not passed through."""
    admitted: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for row in rows:
        try:
            admitted.append(
                filter_public_event(
                    kind=str(row.get("kind") or ""),
                    topic=str(row.get("topic") or ""),
                    payload=dict(row.get("payload") or {}),
                )
            )
        except (HardBanViolation, ValueError) as exc:
            refused.append(
                {
                    "kind": row.get("kind"),
                    "topic": row.get("topic"),
                    "reason": str(exc),
                }
            )
    return {
        "admitted_count": len(admitted),
        "refused_count": len(refused),
        "admitted": admitted,
        "refused": refused,
        "private_leaked": False,
    }
