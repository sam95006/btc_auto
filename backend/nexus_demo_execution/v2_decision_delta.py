"""Honest Decision Delta semantics for 6H V2.

Cost Gate / Geometry / Risk Critic / Data Missing blocks are NOT learning deltas
unless a real trade-case reflection produced a guard change with required fields.
"""
from __future__ import annotations

from typing import Any

REQUIRED_DELTA_FIELDS = (
    "source_trade_case_id",
    "reflection_id",
    "similar_candidate_id",
    "similarity_score",
    "before_verdict",
    "after_verdict",
    "before_score",
    "after_score",
    "guard_action",
    "policy_version",
)

NON_LEARNING_BLOCK_REASONS = frozenset(
    {
        "FEE_RATE_UNKNOWN",
        "FEE_RATE_CONFIG_EXPIRED",
        "BLOCK_COST_DOMINATED_ENTRY",
        "GEOMETRY_INPUT_MISSING",
        "BLOCK_INVALID_STOP_GEOMETRY",
        "BLOCK_UNREACHABLE_TARGET",
        "ROLE_REVIEW_INCOMPLETE",
        "RISK_CRITIC_VETO",
        "MISTAKE_GUARD_BLOCK",
        "DATA_MISSING",
        "STALE_ACCOUNT",
        "SKIP_INSUFFICIENT_SAFE_MARGIN",
    }
)


def is_learning_decision_delta(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("decision_delta") is False:
        return False
    for key in REQUIRED_DELTA_FIELDS:
        val = payload.get(key)
        if val is None or val == "" or val == "MISSING":
            return False
    # Must be tied to a real trade case, not a scan-only block.
    if not str(payload.get("source_trade_case_id") or "").strip():
        return False
    if not str(payload.get("reflection_id") or "").strip():
        return False
    return True


def classify_block_event(reason: str, *, trade_case_id: str | None = None) -> dict[str, Any]:
    """Scan/pretrade blocks are evidence, not learning deltas."""
    r = str(reason or "").strip()
    learning = False
    return {
        "event_type": "PRETRADE_BLOCK" if r in NON_LEARNING_BLOCK_REASONS else "OTHER_BLOCK",
        "reason": r,
        "decision_delta": learning,
        "source_trade_case_id": trade_case_id or "",
        "note": "Cost/geometry/risk/data blocks are not Decision Deltas without reflection fields",
    }


def build_learning_delta(
    *,
    source_trade_case_id: str,
    reflection_id: str,
    similar_candidate_id: str,
    similarity_score: float,
    before_verdict: str,
    after_verdict: str,
    before_score: float,
    after_score: float,
    guard_action: str,
    policy_version: str,
) -> dict[str, Any]:
    payload = {
        "source_trade_case_id": source_trade_case_id,
        "reflection_id": reflection_id,
        "similar_candidate_id": similar_candidate_id,
        "similarity_score": similarity_score,
        "before_verdict": before_verdict,
        "after_verdict": after_verdict,
        "before_score": before_score,
        "after_score": after_score,
        "guard_action": guard_action,
        "policy_version": policy_version,
        "decision_delta": True,
    }
    assert is_learning_decision_delta(payload)
    return payload
