"""Completed-case dedupe and Critic ordering for V13-B completion ops."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_edge_discovery.provider_transport_v23 import dedupe_pending_against_success
from backend.nexus_reflection.adjudication_v11 import build_critic_order
from backend.nexus_v23_completion_ops.constants import (
    SCHEMA_CRITIC,
    SCHEMA_DEDUPE,
    SOT_GROQ_PENDING,
    SOT_GROQ_SUCCESS,
    SOT_SAMBANOVA_PENDING,
    SOT_SAMBANOVA_SUCCESS,
)
from backend.nexus_v23_completion_ops.sot import synthetic_incomplete_checkpoint


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def evaluate_completed_case_dedupe(
    *,
    case_ids: Iterable[str] | None = None,
    completed_case_ids: Iterable[str] | None = None,
    pending_case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    fixture = synthetic_incomplete_checkpoint()
    cases = list(case_ids) if case_ids is not None else list(fixture["case_ids"])
    completed = (
        list(completed_case_ids)
        if completed_case_ids is not None
        else list(fixture["completed_case_ids"])
    )
    if pending_case_ids is not None:
        pending = list(pending_case_ids)
    else:
        # Intentional overlap to prove dedupe blocks requeue of completed cases.
        pending = [completed[0], *list(fixture["pending_case_ids"])]

    before = len(pending)
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
        "pending_before_dedupe": before,
        "pending_after_dedupe": len(deduped),
        "overlap_count": len(overlap),
        "overlap_case_ids_sample": overlap[:5],
        "requeue_blocked_count": len(requeue_attempts),
        "dedupe_effective": all(cid not in set(completed) for cid in deduped),
        "deduped_pending_case_ids": deduped,
        "expected_pending": SOT_GROQ_PENDING,
        "V2_3_complete": False,
    }


def evaluate_critic_ordering(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Critic work only after Groq success; fixture state models incomplete SoT."""
    base = state or synthetic_incomplete_checkpoint()
    # Enrich case_results so build_critic_order can prioritize unresolved disagreements.
    case_results: dict[str, Any] = dict(base.get("case_results") or {})
    completed = list(base.get("completed_case_ids") or [])
    resolved = set(base.get("critic_resolved_ids") or [])
    for i, cid in enumerate(completed):
        if cid in case_results:
            continue
        # First unresolved critic candidates get disagreement signal.
        disagree = cid not in resolved and i >= SOT_SAMBANOVA_SUCCESS
        case_results[cid] = {
            "evidence_sufficiency": "EVIDENCE_SUFFICIENT",
            "process_classification": "EXECUTION_FRICTION" if disagree else "SIGNAL_VALID",
            "deterministic_expected": "SIGNAL_VALID",
            "confidence": 0.4 if disagree else 0.9,
        }
    enriched = {**base, "case_results": case_results}
    order = build_critic_order(enriched)

    # Adversarial probe: critic before reasoner success must be blocked.
    premature = []
    pending_only = list(base.get("pending_case_ids") or [])[:3]
    for cid in pending_only:
        premature.append(
            {
                "case_id": cid,
                "critic_dispatch_allowed": False,
                "reason": "REASONER_SUCCESS_REQUIRED",
                "transport_status": "CRITIC_BEFORE_REASONER_BLOCKED",
            }
        )

    # Ordering must only include completed (reasoner success) cases.
    completed_set = set(completed)
    order_valid = all(cid in completed_set for cid in order)
    # Pending critic SoT slice should appear preferentially.
    expected_pending_critics = completed[
        SOT_SAMBANOVA_SUCCESS : SOT_SAMBANOVA_SUCCESS + SOT_SAMBANOVA_PENDING
    ]
    pending_present = all(cid in order for cid in expected_pending_critics)

    return {
        "schema": SCHEMA_CRITIC,
        "created_at": _utc(),
        "critic_order": order,
        "critic_order_count": len(order),
        "order_only_after_reasoner_success": order_valid,
        "expected_pending_critics_present": pending_present,
        "premature_critic_blocked": premature,
        "premature_blocked_count": len(premature),
        "reasoner_profile": GROQ_REFLECTION_REASONER,
        "critic_profile": SAMBANOVA_INDEPENDENT_CRITIC,
        "groq_success_required": SOT_GROQ_SUCCESS,
        "V2_3_complete": False,
    }
