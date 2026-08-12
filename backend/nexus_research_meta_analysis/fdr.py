"""False-discovery-rate adjustment for cross-experiment meta-analysis."""
from __future__ import annotations

from typing import Any, Sequence

from backend.nexus_research_meta_analysis.constants import BONFERRONI_ALPHA, FDR_Q_LEVEL


def benjamini_hochberg(
    p_values: Sequence[float],
    *,
    q: float = FDR_Q_LEVEL,
) -> dict[str, Any]:
    n = len(p_values)
    if n == 0:
        return {
            "axis": "false_discovery_adjustment",
            "method": "benjamini_hochberg",
            "q": q,
            "n_tests": 0,
            "discoveries": [],
            "rejected_indices": [],
            "adjusted_p": [],
            "development_only": True,
            "not_oos_claim": True,
            "formal_walk_forward": False,
        }

    indexed = sorted(enumerate(float(p) for p in p_values), key=lambda t: t[1])
    adjusted = [1.0] * n
    prev = 1.0
    for rank_from_end, (idx, p) in enumerate(reversed(indexed)):
        rank = n - rank_from_end
        bh = min(prev, (p * n) / rank)
        adjusted[idx] = min(1.0, bh)
        prev = bh

    rejected: list[int] = []
    discoveries: list[dict[str, Any]] = []
    for i, (orig_idx, p) in enumerate(indexed):
        rank = i + 1
        threshold = (rank / n) * q
        if p <= threshold:
            rejected.append(orig_idx)
            discoveries.append(
                {
                    "index": orig_idx,
                    "p_value": p,
                    "bh_threshold": threshold,
                    "rank": rank,
                }
            )

    return {
        "axis": "false_discovery_adjustment",
        "method": "benjamini_hochberg",
        "q": q,
        "n_tests": n,
        "discoveries": discoveries,
        "rejected_indices": sorted(rejected),
        "adjusted_p": adjusted,
        "discovery_count": len(rejected),
        "development_only": True,
        "not_oos_claim": True,
        "formal_walk_forward": False,
    }


def bonferroni_gate(
    p_values: Sequence[float],
    *,
    alpha: float = BONFERRONI_ALPHA,
) -> dict[str, Any]:
    n = len(p_values)
    if n == 0:
        return {
            "method": "bonferroni",
            "alpha": alpha,
            "n_tests": 0,
            "per_test_alpha": None,
            "pass_indices": [],
            "fail_indices": [],
        }
    per = alpha / n
    pass_idx = [i for i, p in enumerate(p_values) if float(p) <= per]
    fail_idx = [i for i in range(n) if i not in set(pass_idx)]
    return {
        "method": "bonferroni",
        "alpha": alpha,
        "n_tests": n,
        "per_test_alpha": per,
        "pass_indices": pass_idx,
        "fail_indices": fail_idx,
        "development_only": True,
        "not_oos_claim": True,
    }
