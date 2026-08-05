"""Allowed development labels only — never qualification / WF / OOS claims."""
from __future__ import annotations

from typing import Any, Mapping

from backend.nexus_research_validation.constants import (
    ALLOWED_LABELS,
    BANNED_LABEL_FRAGMENTS,
)


def assert_label_allowed(label: str) -> str:
    if label not in ALLOWED_LABELS:
        raise ValueError(f"banned or unknown label: {label}")
    upper = label.upper()
    for frag in BANNED_LABEL_FRAGMENTS:
        if frag in upper and label not in ALLOWED_LABELS:
            raise ValueError(f"banned label fragment {frag} in {label}")
    return label


def assign_label(
    *,
    data_quality_blocked: bool,
    sample_sufficient: bool,
    multiple_testing_rejected: bool,
    cost_destroyed: bool,
    bootstrap_stable: bool,
    stability_axes_ok: bool,
    dependence_blocks_robust: bool,
) -> dict[str, Any]:
    """Priority order encodes fail-closed development classification."""
    reasons: list[str] = []
    if data_quality_blocked:
        label = "DATA_QUALITY_BLOCKED"
        reasons.append("data_quality_gate_failed")
    elif not sample_sufficient:
        label = "INSUFFICIENT_SAMPLE"
        reasons.append("sample_size_or_n_eff_below_min")
    elif multiple_testing_rejected:
        label = "MULTIPLE_TESTING_REJECTED"
        reasons.append("bh_or_raw_p_fails_fdr_gate")
    elif cost_destroyed:
        label = "COST_DESTROYED"
        reasons.append("gross_positive_net_nonpositive_or_turnover_destroy")
    elif (
        not bootstrap_stable
        or not stability_axes_ok
        or dependence_blocks_robust
    ):
        label = "DEVELOPMENT_FRAGILE"
        if not bootstrap_stable:
            reasons.append("bootstrap_ci_or_sign_unstable")
        if not stability_axes_ok:
            reasons.append("param_regime_or_symbol_unstable")
        if dependence_blocks_robust:
            reasons.append("ts_dependence_blocks_robust_claim")
    else:
        label = "DEVELOPMENT_ROBUST"
        reasons.append("all_development_robustness_gates_passed")

    assert_label_allowed(label)
    return {
        "label": label,
        "reasons": reasons,
        "qualification_claim": False,
        "formal_walk_forward": False,
        "oos_consumed": False,
        "development_only": True,
        "allowed_labels": sorted(ALLOWED_LABELS),
    }


def label_histogram(results: list[Mapping[str, Any]]) -> dict[str, int]:
    hist = {lab: 0 for lab in sorted(ALLOWED_LABELS)}
    for r in results:
        lab = str(r.get("label") or r.get("result_label") or "")
        assert_label_allowed(lab)
        hist[lab] = hist.get(lab, 0) + 1
    return hist
