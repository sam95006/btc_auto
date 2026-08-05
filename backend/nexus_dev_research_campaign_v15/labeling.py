"""V15-C development labels — never QUALIFIED / profitability claims."""
from __future__ import annotations

from typing import Any, Mapping

from backend.nexus_dev_research_campaign_v15.constants import (
    ALLOWED_LABELS,
    BANNED_LABEL_FRAGMENTS,
)


def assert_label_allowed(label: str) -> str:
    if label not in ALLOWED_LABELS:
        raise ValueError(f"banned or unknown label: {label}")
    upper = label.upper()
    for frag in BANNED_LABEL_FRAGMENTS:
        if frag == "QUALIFIED":
            # DEVELOPMENT_PROMISING_NOT_QUALIFIED contains QUALIFIED substring — allowed.
            if label == "DEVELOPMENT_PROMISING_NOT_QUALIFIED":
                continue
            if "QUALIFIED" in upper and "NOT_QUALIFIED" not in upper:
                raise ValueError(f"banned qualified claim label: {label}")
            continue
        if frag in upper:
            raise ValueError(f"banned label fragment {frag} in {label}")
    return label


def assign_label(
    *,
    data_blocked: bool,
    sample_blocked: bool,
    multiple_testing_rejected: bool,
    cost_destroyed: bool,
    regime_fragile: bool,
    development_promising: bool,
    rejected: bool,
) -> dict[str, Any]:
    """Fail-closed priority order for V15-C development classification."""
    reasons: list[str] = []
    if data_blocked:
        label = "DATA_BLOCKED"
        reasons.append("required_features_unavailable_or_data_quality_gate")
    elif sample_blocked:
        label = "SAMPLE_BLOCKED"
        reasons.append("trade_or_observation_count_below_min")
    elif multiple_testing_rejected:
        label = "MULTIPLE_TESTING_REJECTED"
        reasons.append("bh_fdr_or_family_multiplicity_reject")
    elif cost_destroyed:
        label = "COST_DESTROYED"
        reasons.append("gross_positive_net_nonpositive_after_full_costs")
    elif regime_fragile:
        label = "REGIME_FRAGILE"
        reasons.append("regime_concentration_above_fragility_share")
    elif development_promising:
        label = "DEVELOPMENT_PROMISING_NOT_QUALIFIED"
        reasons.append("development_gates_passed_NOT_qualified")
    elif rejected:
        label = "REJECTED"
        reasons.append("economic_or_sign_failure_on_development")
    else:
        label = "DEVELOPMENT_REVIEW"
        reasons.append("inconclusive_development_evidence_needs_review")

    assert_label_allowed(label)
    return {
        "label": label,
        "reasons": reasons,
        "qualification_claim": False,
        "formal_walk_forward": False,
        "oos_consumed": False,
        "development_only": True,
        "profitability_claimed": False,
        "allowed_labels": sorted(ALLOWED_LABELS),
    }


def label_histogram(results: list[Mapping[str, Any]]) -> dict[str, int]:
    hist = {lab: 0 for lab in sorted(ALLOWED_LABELS)}
    for r in results:
        lab = str(r.get("label") or r.get("result_label") or "")
        assert_label_allowed(lab)
        hist[lab] = hist.get(lab, 0) + 1
    return hist
