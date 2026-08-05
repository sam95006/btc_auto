"""Experiment duplication detection."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.nexus_research_meta_analysis.constants import (
    DUPLICATE_IDENTITY_CORR_FLOOR,
    DUPLICATE_PARAM_DISTANCE_MAX,
)
from backend.nexus_research_meta_analysis.correlation import _pearson


def _param_distance(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    keys = sorted(set(a) | set(b))
    if not keys:
        return 0.0
    diffs = []
    for k in keys:
        va = float(a.get(k, 0.0))
        vb = float(b.get(k, 0.0))
        scale = max(abs(va), abs(vb), 1e-9)
        diffs.append(abs(va - vb) / scale)
    return sum(diffs) / len(diffs)


def detect_duplicates(
    experiments: Sequence[Mapping[str, Any]],
    *,
    corr_floor: float = DUPLICATE_IDENTITY_CORR_FLOOR,
    param_max: float = DUPLICATE_PARAM_DISTANCE_MAX,
) -> dict[str, Any]:
    ids = [str(e["experiment_id"]) for e in experiments]
    by_id = {str(e["experiment_id"]): e for e in experiments}
    pairs: list[dict[str, Any]] = []
    duplicate_ids: set[str] = set()

    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            ea, eb = by_id[a], by_id[b]
            same_mech = ea["mechanism_semantic_id"] == eb["mechanism_semantic_id"]
            same_family = ea["research_family"] == eb["research_family"]
            corr = _pearson(ea["net_series"], eb["net_series"])
            pdist = _param_distance(ea.get("parameters") or {}, eb.get("parameters") or {})
            is_dup = (
                same_mech
                and same_family
                and abs(corr) >= corr_floor
                and pdist <= param_max
            )
            if is_dup:
                duplicate_ids.add(a)
                duplicate_ids.add(b)
                pairs.append(
                    {
                        "a": a,
                        "b": b,
                        "correlation": corr,
                        "param_distance": pdist,
                        "mechanism_semantic_id": ea["mechanism_semantic_id"],
                        "duplicate": True,
                    }
                )

    return {
        "axis": "experiment_duplication",
        "corr_floor": corr_floor,
        "param_distance_max": param_max,
        "duplicate_pair_count": len(pairs),
        "duplicate_pairs": pairs,
        "duplicate_experiment_ids": sorted(duplicate_ids),
        "development_only": True,
        "not_oos_claim": True,
    }
