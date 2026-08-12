"""Candidate correlation clustering (development / synthetic only)."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.nexus_research_validation.constants import CORRELATION_CLUSTER_THRESHOLD


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    xa = list(a[:n])
    xb = list(b[:n])
    ma = sum(xa) / n
    mb = sum(xb) / n
    num = sum((xa[i] - ma) * (xb[i] - mb) for i in range(n))
    da = sum((x - ma) ** 2 for x in xa) ** 0.5
    db = sum((x - mb) ** 2 for x in xb) ** 0.5
    if da < 1e-18 or db < 1e-18:
        return 0.0
    return max(-1.0, min(1.0, num / (da * db)))


def correlation_matrix(
    series_by_id: Mapping[str, Sequence[float]],
) -> dict[str, Any]:
    ids = sorted(series_by_id)
    matrix: dict[str, dict[str, float]] = {}
    for i in ids:
        matrix[i] = {}
        for j in ids:
            if i == j:
                matrix[i][j] = 1.0
            elif j in matrix and i in matrix[j]:
                matrix[i][j] = matrix[j][i]
            else:
                matrix[i][j] = _pearson(series_by_id[i], series_by_id[j])
    return {"ids": ids, "matrix": matrix}


def cluster_candidates(
    series_by_id: Mapping[str, Sequence[float]],
    *,
    threshold: float = CORRELATION_CLUSTER_THRESHOLD,
) -> dict[str, Any]:
    """Greedy absolute-correlation clustering above threshold."""
    ids = sorted(series_by_id)
    corr = correlation_matrix(series_by_id)
    matrix = corr["matrix"]
    assigned: dict[str, int] = {}
    clusters: list[list[str]] = []
    for cid in ids:
        if cid in assigned:
            continue
        cluster_idx = len(clusters)
        members = [cid]
        assigned[cid] = cluster_idx
        for other in ids:
            if other in assigned:
                continue
            if abs(matrix[cid][other]) >= threshold:
                assigned[other] = cluster_idx
                members.append(other)
        clusters.append(sorted(members))

    redundant_pairs: list[dict[str, Any]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            r = matrix[a][b]
            if abs(r) >= threshold:
                redundant_pairs.append(
                    {
                        "a": a,
                        "b": b,
                        "correlation": r,
                        "same_cluster": assigned[a] == assigned[b],
                    }
                )

    return {
        "threshold": threshold,
        "candidate_count": len(ids),
        "cluster_count": len(clusters),
        "clusters": [
            {"cluster_id": f"CORR_CLUSTER_{i:03d}", "members": members}
            for i, members in enumerate(clusters)
        ],
        "assignment": {k: f"CORR_CLUSTER_{v:03d}" for k, v in assigned.items()},
        "redundant_pair_count": len(redundant_pairs),
        "redundant_pairs": redundant_pairs,
        "correlation_matrix": matrix,
        "development_only": True,
        "not_oos_claim": True,
        "formal_walk_forward": False,
    }
