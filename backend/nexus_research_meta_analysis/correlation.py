"""Candidate and mechanism-family correlation analysis."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.nexus_research_meta_analysis.constants import (
    CANDIDATE_CORR_THRESHOLD,
    FAMILY_CORR_THRESHOLD,
)


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


def candidate_correlation(
    series_by_id: Mapping[str, Sequence[float]],
    *,
    threshold: float = CANDIDATE_CORR_THRESHOLD,
) -> dict[str, Any]:
    ids = sorted(series_by_id)
    matrix: dict[str, dict[str, float]] = {i: {} for i in ids}
    high_pairs: list[dict[str, Any]] = []
    for i, a in enumerate(ids):
        for b in ids[i:]:
            if a == b:
                matrix[a][b] = 1.0
                continue
            r = _pearson(series_by_id[a], series_by_id[b])
            matrix[a][b] = r
            matrix[b][a] = r
            if abs(r) >= threshold:
                high_pairs.append({"a": a, "b": b, "correlation": r})
    return {
        "axis": "candidate_correlation",
        "threshold": threshold,
        "ids": ids,
        "matrix": matrix,
        "high_correlation_pair_count": len(high_pairs),
        "high_correlation_pairs": high_pairs,
        "development_only": True,
        "not_oos_claim": True,
    }


def mechanism_family_correlation(
    experiments: Sequence[Mapping[str, Any]],
    *,
    threshold: float = FAMILY_CORR_THRESHOLD,
) -> dict[str, Any]:
    """Correlate mean net-series across mechanism families (family centroids)."""
    by_family: dict[str, list[list[float]]] = {}
    for e in experiments:
        fam = str(e["research_family"])
        by_family.setdefault(fam, []).append(list(e["net_series"]))

    centroids: dict[str, list[float]] = {}
    for fam, series_list in by_family.items():
        n = min(len(s) for s in series_list)
        if n == 0:
            centroids[fam] = []
            continue
        centroid = []
        for t in range(n):
            centroid.append(sum(s[t] for s in series_list) / len(series_list))
        centroids[fam] = centroid

    ids = sorted(centroids)
    matrix: dict[str, dict[str, float]] = {i: {} for i in ids}
    high_pairs: list[dict[str, Any]] = []
    for i, a in enumerate(ids):
        for b in ids[i:]:
            if a == b:
                matrix[a][b] = 1.0
                continue
            r = _pearson(centroids[a], centroids[b])
            matrix[a][b] = r
            matrix[b][a] = r
            if abs(r) >= threshold:
                high_pairs.append({"a": a, "b": b, "correlation": r})

    return {
        "axis": "mechanism_family_correlation",
        "threshold": threshold,
        "families": ids,
        "family_member_counts": {f: len(by_family[f]) for f in ids},
        "matrix": matrix,
        "high_correlation_pair_count": len(high_pairs),
        "high_correlation_pairs": high_pairs,
        "development_only": True,
        "not_oos_claim": True,
    }
