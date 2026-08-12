"""Similarity query contract for Decision Memory Graph."""
from __future__ import annotations

from typing import Any

from backend.nexus_decision_memory_graph.constants import SIMILARITY_CONTRACT, SCHEMA_VERSION
from backend.nexus_decision_memory_graph.hashing import sha256_hex


class SimilarityQueryError(ValueError):
    """Fail-closed similarity contract violation."""


REQUIRED_QUERY_KEYS: tuple[str, ...] = (
    "schema",
    "schema_version",
    "query_id",
    "as_of_ms",
    "pit_bound",
    "anchor_node_id",
    "dimensions",
    "limit",
)


def build_similarity_query(
    *,
    query_id: str,
    as_of_ms: int,
    anchor_node_id: str,
    dimensions: dict[str, Any] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Build a versioned similarity query (contract only — no ranking claims)."""
    if limit < 1 or limit > 100:
        raise SimilarityQueryError("similarity_limit_out_of_range")
    if as_of_ms < 0:
        raise SimilarityQueryError("similarity_as_of_ms_invalid")
    dims = dict(dimensions or {})
    q = {
        "schema": SIMILARITY_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "query_id": str(query_id),
        "as_of_ms": int(as_of_ms),
        "pit_bound": True,
        "anchor_node_id": str(anchor_node_id),
        "dimensions": dims,
        "limit": int(limit),
        "ranking_claim": False,
        "profitability_claim": False,
    }
    q["query_hash"] = sha256_hex(
        {k: q[k] for k in REQUIRED_QUERY_KEYS if k in q}
    )
    return q


def validate_similarity_query(query: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in REQUIRED_QUERY_KEYS if k not in query]
    if missing:
        raise SimilarityQueryError(f"similarity_query_missing:{missing}")
    if query.get("schema") != SIMILARITY_CONTRACT:
        raise SimilarityQueryError("similarity_schema_mismatch")
    if int(query.get("schema_version", -1)) != SCHEMA_VERSION:
        raise SimilarityQueryError("similarity_schema_version_mismatch")
    if not query.get("pit_bound", False):
        raise SimilarityQueryError("similarity_must_be_pit_bound")
    if query.get("ranking_claim") or query.get("profitability_claim"):
        raise SimilarityQueryError("similarity_claims_forbidden")
    return {"ok": True, "query_id": query["query_id"]}


def score_similarity(
    anchor: dict[str, Any],
    candidate: dict[str, Any],
    dimensions: dict[str, Any],
) -> float:
    """Deterministic overlap score in [0, 1] over declared dimensions.

    Uses tag/label intersection only — not a performance claim.
    """
    if not dimensions:
        return 0.0
    score = 0.0
    weight_sum = 0.0
    a_payload = anchor.get("payload") if isinstance(anchor.get("payload"), dict) else {}
    c_payload = candidate.get("payload") if isinstance(candidate.get("payload"), dict) else {}
    for dim, weight in dimensions.items():
        w = float(weight)
        weight_sum += abs(w)
        a_val = a_payload.get(dim)
        c_val = c_payload.get(dim)
        if a_val is None or c_val is None:
            continue
        if isinstance(a_val, (list, tuple, set)) and isinstance(c_val, (list, tuple, set)):
            sa, sc = set(map(str, a_val)), set(map(str, c_val))
            if sa or sc:
                score += w * (len(sa & sc) / max(len(sa | sc), 1))
        elif str(a_val) == str(c_val):
            score += w
    if weight_sum <= 0:
        return 0.0
    return max(0.0, min(1.0, score / weight_sum))
