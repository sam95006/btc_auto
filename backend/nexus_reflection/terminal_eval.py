"""Terminal evaluation gate — quality only when Groq=80 and critics resolved."""
from __future__ import annotations

from typing import Any

from backend.nexus_edge_discovery.quota_aware_v23 import evaluate_quality as _evaluate_quality
from backend.nexus_edge_discovery.ratio_metrics import make_ratio
from backend.nexus_reflection.checkpoint import validate_counter_invariants
from backend.nexus_reflection.disagreement import ALLOWED_CONFLICT_TYPES


def validate_terminal_denominators(quality: dict[str, Any]) -> dict[str, Any]:
    """Zero-denominator ratios must be NOT_APPLICABLE (never fake 0/1)."""
    issues: list[str] = []
    for key, val in quality.items():
        if not isinstance(val, dict):
            continue
        if "numerator" not in val or "denominator" not in val:
            continue
        den = val.get("denominator")
        status = val.get("status")
        value = val.get("value")
        try:
            d = float(den)
        except (TypeError, ValueError):
            continue
        if d <= 0:
            if status != "NOT_APPLICABLE" and status not in {
                "PROVIDER_BLOCKED",
                "GROQ_PROVIDER_BLOCKED",
                "SAMBANOVA_PROVIDER_BLOCKED",
                "PROVIDER_CAPACITY_UNKNOWN",
            }:
                issues.append(f"{key}:zero_denom_status={status}")
            if value is not None:
                issues.append(f"{key}:zero_denom_value={value}")
    return {
        "terminal_denominator_validation": "PASS" if not issues else "FAIL",
        "issues": issues,
    }


def reconcile_provider_success_counts(state: dict[str, Any]) -> dict[str, Any]:
    """Reconcile transport success_count with completed/resolved lists; never inflate."""
    probe = validate_counter_invariants(state)
    completed = int(probe["completed_case_count"])
    resolved = int(probe["critic_resolved_count"])
    # Capacity gate uses the list length only when counters reconcile; otherwise
    # fail closed at the lower (list) bound so inflated counters cannot pass ≥80.
    groq_for_gate = completed if probe["ok"] else min(int(probe["groq_success_count"]), completed)
    return {
        **probe,
        "groq_success_count_for_gate": groq_for_gate,
        "critic_resolved_count_for_gate": resolved if probe["ok"] else min(int(probe["critic_success_count"]), resolved),
        "refused_inflated_counter": not probe["ok"],
    }


def evaluate_terminal(state: dict[str, Any]) -> dict[str, Any]:
    """Wrap frozen quality gates; do not evaluate until groq_success=80 + critics done."""
    groq = (state.get("transport") or {}).get("GROQ_REFLECTION_REASONER") or {}
    recon = reconcile_provider_success_counts(state)
    groq_success = int(recon["groq_success_count_for_gate"])

    quality = _evaluate_quality(state)
    denom = validate_terminal_denominators(quality)

    critic_required = len(state.get("critic_case_ids") or [])
    critic_resolved = len(state.get("critic_resolved_ids") or [])
    critics_complete = critic_required == 0 or critic_resolved == critic_required

    if recon["refused_inflated_counter"]:
        quality["quality_gates_evaluated"] = False
        quality["quality_gates_passed"] = False
        quality["V2_3_TERMINAL_STATUS"] = "CHECKPOINT_COUNTER_DRIFT"
        quality["counter_invariant_status"] = "FAIL_CLOSED"
        quality["counter_invariant_issues"] = list(recon.get("issues") or [])
    elif groq_success < 80 or not critics_complete:
        quality["quality_gates_evaluated"] = False
        quality["quality_gates_passed"] = False
        if quality.get("V2_3_TERMINAL_STATUS") == "VERIFIED":
            quality["V2_3_TERMINAL_STATUS"] = "INCOMPLETE_PROVIDER_CAPACITY"
        sn_429 = int(
            ((state.get("transport") or {}).get("SAMBANOVA_INDEPENDENT_CRITIC") or {}).get(
                "HTTP_429_count"
            )
            or 0
        )
        groq_429 = int(groq.get("HTTP_429_count") or 0)
        if groq_success < 80 or sn_429 > 0 or groq_429 > 0 or not critics_complete:
            quality["V2_3_TERMINAL_STATUS"] = "INCOMPLETE_PROVIDER_CAPACITY"
        elif quality.get("V2_3_TERMINAL_STATUS") not in {
            "INCOMPLETE_PROVIDER_CAPACITY",
            "INCOMPLETE",
            "VALID_SAMPLE_QUALITY_FAILED",
        }:
            quality["V2_3_TERMINAL_STATUS"] = "INCOMPLETE"
        quality["counter_invariant_status"] = "OK"
    else:
        quality["counter_invariant_status"] = "OK"

    quality["terminal_denominator_validation"] = denom
    quality["allowed_conflict_types"] = list(ALLOWED_CONFLICT_TYPES)
    quality["groq_success_count"] = groq_success
    quality["critic_required_count"] = critic_required
    quality["critic_resolved_count"] = critic_resolved
    quality["frozen_quality_gates_unchanged"] = True
    quality["counter_reconciliation"] = {
        "ok": recon["ok"],
        "refused_inflated_counter": recon["refused_inflated_counter"],
        "issues": list(recon.get("issues") or []),
    }
    return quality


def zero_denom_ratio() -> dict[str, Any]:
    return make_ratio(0, 0)
