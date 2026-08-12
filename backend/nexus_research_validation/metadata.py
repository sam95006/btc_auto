"""Multiple-comparison metadata for development research families."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.nexus_research_validation.constants import BONFERRONI_ALPHA, FDR_Q_LEVEL
from backend.nexus_research_validation.fdr import benjamini_hochberg, bonferroni_gate


def multiple_comparison_metadata(
    *,
    family_id: str,
    candidate_ids: Sequence[str],
    p_values: Sequence[float],
    hypotheses: Sequence[str] | None = None,
) -> dict[str, Any]:
    if len(candidate_ids) != len(p_values):
        raise ValueError("candidate_ids and p_values length mismatch")
    n = len(p_values)
    hyps = list(hypotheses) if hypotheses is not None else [
        f"H0_no_dev_edge::{cid}" for cid in candidate_ids
    ]
    if len(hyps) != n:
        raise ValueError("hypotheses length mismatch")

    bh = benjamini_hochberg(p_values, q=FDR_Q_LEVEL)
    bonf = bonferroni_gate(p_values, alpha=BONFERRONI_ALPHA)
    per_candidate: list[dict[str, Any]] = []
    for i, cid in enumerate(candidate_ids):
        per_candidate.append(
            {
                "candidate_id": cid,
                "hypothesis": hyps[i],
                "raw_p": float(p_values[i]),
                "bh_adjusted_p": float(bh["adjusted_p"][i]),
                "bh_discovery": i in bh["rejected_indices"],
                "bonferroni_pass": i in bonf["pass_indices"],
                "family_test_count": n,
                "development_only": True,
                "not_oos_significance": True,
            }
        )
    return {
        "schema": "v14_d_multiple_comparison_metadata",
        "family_id": family_id,
        "n_tests": n,
        "fdr_q": FDR_Q_LEVEL,
        "bonferroni_alpha": BONFERRONI_ALPHA,
        "bh": bh,
        "bonferroni": bonf,
        "per_candidate": per_candidate,
        "formal_walk_forward": False,
        "oos_consumed": False,
        "qualification_claim": False,
    }


def family_comparison_bundle(
    families: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """families[family_id] = {candidate_ids, p_values, hypotheses?}"""
    out: dict[str, Any] = {}
    total_tests = 0
    total_bh_discoveries = 0
    for fam, payload in sorted(families.items()):
        meta = multiple_comparison_metadata(
            family_id=fam,
            candidate_ids=list(payload["candidate_ids"]),
            p_values=list(payload["p_values"]),
            hypotheses=payload.get("hypotheses"),
        )
        out[fam] = meta
        total_tests += meta["n_tests"]
        total_bh_discoveries += int(meta["bh"]["discovery_count"])
    return {
        "schema": "v14_d_family_comparison_bundle",
        "family_count": len(out),
        "total_tests": total_tests,
        "total_bh_discoveries": total_bh_discoveries,
        "families": out,
        "development_only": True,
        "not_oos_claim": True,
    }
