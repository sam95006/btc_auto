"""Completed-case dedupe — never re-queue successful cases in ops scheduling views."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from backend.nexus_edge_discovery.provider_transport_v23 import dedupe_pending_against_success
from backend.nexus_provider_ops.constants import (
    SCHEMA_DEDUPE,
    SOT_GROQ_PENDING,
    SOT_GROQ_SUCCESS,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_case_ids(n: int = 80) -> list[str]:
    return [f"case_{i:03d}" for i in range(n)]


def evaluate_completed_case_dedupe(
    *,
    case_ids: Iterable[str] | None = None,
    completed_case_ids: Iterable[str] | None = None,
    pending_case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Dedupe pending against completed using transport authority helper."""
    cases = list(case_ids) if case_ids is not None else _default_case_ids()
    if completed_case_ids is not None:
        completed = list(completed_case_ids)
    else:
        completed = cases[:SOT_GROQ_SUCCESS]
    if pending_case_ids is not None:
        pending = list(pending_case_ids)
    else:
        # Include intentional overlap to prove dedupe: first completed reappears in pending
        pending = [completed[0], *cases[SOT_GROQ_SUCCESS : SOT_GROQ_SUCCESS + SOT_GROQ_PENDING]]

    before_count = len(pending)
    overlap = sorted(set(completed) & set(pending))
    deduped = dedupe_pending_against_success(
        case_ids=cases,
        completed_case_ids=completed,
        pending_case_ids=pending,
    )
    requeue_attempts = [cid for cid in pending if cid in set(completed)]
    return {
        "schema": SCHEMA_DEDUPE,
        "created_at": _utc(),
        "case_id_count": len(cases),
        "completed_case_count": len(set(completed)),
        "pending_before_dedupe": before_count,
        "pending_after_dedupe": len(deduped),
        "overlap_count": len(overlap),
        "overlap_case_ids_sample": overlap[:5],
        "requeue_blocked_count": len(requeue_attempts),
        "dedupe_effective": all(cid not in set(completed) for cid in deduped),
        "deduped_pending_case_ids": deduped,
        "V2_3_complete": False,
    }
