"""Triage classification engine — development statuses only."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_candidate_triage.bans import assert_status_allowed, sanitize_triage_record
from backend.nexus_candidate_triage.constants import (
    ALLOWED_TRIAGE_STATUSES,
    BLOCK_REASON,
    EVIDENCE_CLASS,
    FORBIDDEN_OUTPUT_STATUSES,
    SCHEMA_ID,
    TRIAGE_PRIORITY,
)


MIN_SAMPLE_N = 200


def _signals(candidate: dict[str, Any]) -> list[str]:
    """Collect all matching triage signals (unordered)."""
    hits: list[str] = []
    cost = dict(candidate.get("cost_sensitivity") or {})
    rob = dict(candidate.get("robustness") or {})
    regime = dict(candidate.get("regime") or {})
    signals = dict(candidate.get("signals") or {})

    data_bad = (not bool(candidate.get("data_quality_ok", True))) or (
        not bool(candidate.get("pit_ok", True))
    )
    if data_bad or rob.get("label") == "DATA_QUALITY_BLOCKED":
        hits.append("DATA_BLOCKED")

    sample_n = int(candidate.get("sample_n") or 0)
    if sample_n < MIN_SAMPLE_N or rob.get("label") == "INSUFFICIENT_SAMPLE" or (
        rob.get("sample_sufficient") is False
    ):
        hits.append("SAMPLE_BLOCKED")

    if bool(cost.get("cost_destroyed")) or rob.get("label") == "COST_DESTROYED":
        hits.append("COST_DESTROYED")

    if bool(regime.get("fragile")) or (
        rob.get("label") == "DEVELOPMENT_FRAGILE" and bool(regime.get("fragile"))
    ):
        hits.append("REGIME_FRAGILE")

    if bool(signals.get("rejected")) or rob.get("label") == "MULTIPLE_TESTING_REJECTED":
        hits.append("REJECTED")

    if bool(signals.get("promising")) and rob.get("label") == "DEVELOPMENT_ROBUST":
        hits.append("DEVELOPMENT_PROMISING_NOT_QUALIFIED")

    # DEVELOPMENT_REVIEW: fragile-but-not-regime, or explicit needs_review, and not
    # already classified into a more restrictive / promising bucket by priority.
    if bool(signals.get("needs_review")) or (
        rob.get("label") == "DEVELOPMENT_FRAGILE" and not bool(regime.get("fragile"))
    ):
        hits.append("DEVELOPMENT_REVIEW")

    return hits


def resolve_status(hits: list[str]) -> str:
    """Pick most restrictive status by TRIAGE_PRIORITY."""
    if not hits:
        return "DEVELOPMENT_REVIEW"
    for status in TRIAGE_PRIORITY:
        if status in hits:
            assert_status_allowed(status)
            return status
    return "DEVELOPMENT_REVIEW"


def classify_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    hits = _signals(candidate)
    status = resolve_status(hits)
    assert_status_allowed(status)
    if status in FORBIDDEN_OUTPUT_STATUSES:
        raise RuntimeError(f"FORBIDDEN_OUTPUT_STATUS:{status}")

    reasons: list[str] = []
    if "DATA_BLOCKED" in hits:
        reasons.append("data_quality_or_pit_failed")
    if "SAMPLE_BLOCKED" in hits:
        reasons.append("insufficient_sample")
    if "COST_DESTROYED" in hits:
        reasons.append("net_expectancy_destroyed_by_cost")
    if "REGIME_FRAGILE" in hits:
        reasons.append("regime_fragility")
    if "REJECTED" in hits:
        reasons.append("rejected_or_multiple_testing")
    if "DEVELOPMENT_REVIEW" in hits:
        reasons.append("development_review_required")
    if "DEVELOPMENT_PROMISING_NOT_QUALIFIED" in hits:
        reasons.append("development_promising_not_qualified")

    record = {
        "candidate_id": candidate.get("candidate_id"),
        "triage_status": status,
        "signal_hits": hits,
        "reasons": reasons,
        "priority_order": list(TRIAGE_PRIORITY),
        "qualified": False,
        "selected": False,
        "promoted": False,
        "demo_ready": False,
        "qualification_ready": False,
        "formal_walk_forward_executed": False,
        "oos_touched": False,
        "block_reason": BLOCK_REASON,
        "evidence_class": EVIDENCE_CLASS,
        "fixture_only": bool(candidate.get("fixture_only", True)),
        "candidate_checksum": candidate.get("candidate_checksum"),
        "mechanism_semantic_id": (candidate.get("mechanism") or {}).get("mechanism_semantic_id"),
        "sample_n": candidate.get("sample_n"),
        "net_expectancy": (candidate.get("cost_sensitivity") or {}).get("net_expectancy"),
        "gross_expectancy": (candidate.get("cost_sensitivity") or {}).get("gross_expectancy"),
        "robustness_label": (candidate.get("robustness") or {}).get("label"),
    }
    return sanitize_triage_record(record)


def triage_bundle(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    results = [classify_candidate(c) for c in candidates]
    histogram: dict[str, int] = {s: 0 for s in ALLOWED_TRIAGE_STATUSES}
    for r in results:
        histogram[r["triage_status"]] = histogram.get(r["triage_status"], 0) + 1

    forbidden_emitted = [
        r["candidate_id"]
        for r in results
        if r["triage_status"] in FORBIDDEN_OUTPUT_STATUSES
    ]
    if forbidden_emitted:
        raise RuntimeError(f"FORBIDDEN_OUTPUT_EMITTED:{forbidden_emitted}")

    return {
        "schema": SCHEMA_ID,
        "results": results,
        "status_histogram": histogram,
        "triaged_count": len(results),
        "qualification_ready_count": 0,
        "qualified_count": 0,
        "promoted_count": 0,
        "demo_ready_count": 0,
        "forbidden_output_count": 0,
        "allowed_statuses_only": True,
        "all_fixture_only": all(r.get("fixture_only") for r in results),
        "evidence_class": EVIDENCE_CLASS,
    }


def expect_histogram_coverage(histogram: dict[str, int]) -> bool:
    """Fixture bundle should exercise every allowed status at least once."""
    return all(histogram.get(s, 0) >= 1 for s in ALLOWED_TRIAGE_STATUSES)


def inject_forbidden_status_attempt(candidate: dict[str, Any], status: str) -> dict[str, Any]:
    """Adversarial helper: prove engine refuses forbidden statuses."""
    poisoned = deepcopy(candidate)
    poisoned["forced_triage_status"] = status
    # Engine ignores forced_triage_status — classify from evidence only.
    record = classify_candidate(poisoned)
    if record["triage_status"] in FORBIDDEN_OUTPUT_STATUSES:
        raise RuntimeError(f"FORBIDDEN_OUTPUT_STATUS:{record['triage_status']}")
    return {
        "attempted_status": status,
        "emitted_status": record["triage_status"],
        "forbidden_accepted": False,
        "record": record,
    }
