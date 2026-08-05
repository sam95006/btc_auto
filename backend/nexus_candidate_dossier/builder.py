"""Build complete development candidate dossiers (status-capped)."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from backend.nexus_candidate_dossier.bans import assert_status_allowed, sanitize_dossier
from backend.nexus_candidate_dossier.constants import (
    ALLOWED_DOSSIER_STATUSES,
    BLOCK_REASON,
    EVIDENCE_CLASS,
    FORBIDDEN_OUTPUT_STATUSES,
    REQUIRED_DOSSIER_FIELDS,
    SCHEMA_ID,
)


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _require_fields(candidate: dict[str, Any]) -> None:
    required = [f for f in REQUIRED_DOSSIER_FIELDS if f != "dossier_status"] + ["dossier_status"]
    missing = [key for key in required if key not in candidate]
    if missing:
        raise RuntimeError(f"DOSSIER_INPUT_MISSING_FIELDS:{sorted(set(missing))}")


def build_dossier(candidate: dict[str, Any]) -> dict[str, Any]:
    """Assemble one development dossier. Status ceiling enforced."""
    _require_fields(candidate)
    status = str(candidate["dossier_status"])
    assert_status_allowed(status)
    if status in FORBIDDEN_OUTPUT_STATUSES:
        raise RuntimeError(f"FORBIDDEN_OUTPUT_STATUS:{status}")

    mech = dict(candidate.get("semantic_mechanism") or {})
    dossier = {
        "schema": SCHEMA_ID,
        "candidate_id": candidate.get("candidate_id"),
        "dossier_status": status,
        "semantic_mechanism": mech,
        "economic_rationale": candidate.get("economic_rationale"),
        "data_lineage": deepcopy(candidate.get("data_lineage")),
        "universe_checksum": candidate.get("universe_checksum"),
        "feature_version": candidate.get("feature_version"),
        "feature_ids": list(candidate.get("feature_ids") or []),
        "code_checksum": candidate.get("code_checksum"),
        "parameter_checksum": candidate.get("parameter_checksum"),
        "cost_version": candidate.get("cost_version"),
        "risk_version": candidate.get("risk_version"),
        "execution_version": candidate.get("execution_version"),
        "development_intervals": deepcopy(candidate.get("development_intervals") or []),
        "failed_sibling_experiments": deepcopy(
            candidate.get("failed_sibling_experiments") or []
        ),
        "regime_breakdown": deepcopy(candidate.get("regime_breakdown") or {}),
        "symbol_breakdown": deepcopy(candidate.get("symbol_breakdown") or {}),
        "cost_breakdown": deepcopy(candidate.get("cost_breakdown") or {}),
        "capacity_assumptions": deepcopy(candidate.get("capacity_assumptions") or {}),
        "known_failure_conditions": list(candidate.get("known_failure_conditions") or []),
        "multiple_testing_status": candidate.get("multiple_testing_status"),
        "remaining_blockers": list(candidate.get("remaining_blockers") or []),
        "sample_n": candidate.get("sample_n"),
        "candidate_checksum": candidate.get("candidate_checksum"),
        "parameters": deepcopy(candidate.get("parameters") or {}),
        "qualified": False,
        "selected": False,
        "promoted": False,
        "demo_ready": False,
        "qualification_ready": False,
        "formal_walk_forward_executed": False,
        "oos_touched": False,
        "profitability_claim": False,
        "fixture_only": bool(candidate.get("fixture_only", True)),
        "evidence_class": EVIDENCE_CLASS,
        "block_reason": BLOCK_REASON,
        "as_of_ms": candidate.get("as_of_ms"),
    }
    missing_out = [f for f in REQUIRED_DOSSIER_FIELDS if f not in dossier or dossier[f] in (None, "")]
    if missing_out:
        raise RuntimeError(f"DOSSIER_OUTPUT_MISSING_FIELDS:{missing_out}")

    dossier["dossier_checksum"] = _sha(
        {
            "candidate_id": dossier["candidate_id"],
            "dossier_status": dossier["dossier_status"],
            "universe_checksum": dossier["universe_checksum"],
            "code_checksum": dossier["code_checksum"],
            "parameter_checksum": dossier["parameter_checksum"],
            "feature_version": dossier["feature_version"],
            "cost_version": dossier["cost_version"],
            "risk_version": dossier["risk_version"],
            "execution_version": dossier["execution_version"],
            "failed_sibling_ids": [
                s.get("experiment_id") for s in dossier["failed_sibling_experiments"]
            ],
            "intervals": dossier["development_intervals"],
        }
    )
    return sanitize_dossier(dossier)


def build_dossier_bundle(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    dossiers = [build_dossier(c) for c in candidates]
    histogram: dict[str, int] = {s: 0 for s in ALLOWED_DOSSIER_STATUSES}
    for d in dossiers:
        histogram[d["dossier_status"]] = histogram.get(d["dossier_status"], 0) + 1

    forbidden = [
        d["candidate_id"]
        for d in dossiers
        if d["dossier_status"] in FORBIDDEN_OUTPUT_STATUSES
        or d["dossier_status"] not in ALLOWED_DOSSIER_STATUSES
    ]
    if forbidden:
        raise RuntimeError(f"FORBIDDEN_OR_OVER_CEILING_STATUS:{forbidden}")

    for d in dossiers:
        if not d.get("failed_sibling_experiments"):
            raise RuntimeError(f"MISSING_FAILED_SIBLINGS:{d.get('candidate_id')}")

    return {
        "schema": SCHEMA_ID,
        "dossiers": dossiers,
        "status_histogram": histogram,
        "dossier_count": len(dossiers),
        "qualification_ready_count": 0,
        "qualified_count": 0,
        "promoted_count": 0,
        "demo_ready_count": 0,
        "forbidden_output_count": 0,
        "allowed_statuses_only": True,
        "status_ceiling_ok": True,
        "all_fixture_only": all(d.get("fixture_only") for d in dossiers),
        "all_have_failed_siblings": all(
            bool(d.get("failed_sibling_experiments")) for d in dossiers
        ),
        "all_required_fields_present": all(
            all(f in d for f in REQUIRED_DOSSIER_FIELDS) for d in dossiers
        ),
        "bundle_digest": _sha(
            {
                "ids": [d["candidate_id"] for d in dossiers],
                "checksums": [d["dossier_checksum"] for d in dossiers],
                "histogram": histogram,
            }
        ),
    }


def inject_forbidden_status_attempt(
    candidate: dict[str, Any], forbidden_status: str
) -> dict[str, Any]:
    """Adversarial: attempt to emit a forbidden / over-ceiling status; must fail closed."""
    poisoned = deepcopy(candidate)
    poisoned["dossier_status"] = forbidden_status
    try:
        build_dossier(poisoned)
        return {
            "forbidden_status": forbidden_status,
            "forbidden_accepted": True,
            "error": None,
        }
    except RuntimeError as exc:
        return {
            "forbidden_status": forbidden_status,
            "forbidden_accepted": False,
            "error": str(exc),
        }


def expect_histogram_coverage(histogram: dict[str, int]) -> bool:
    return all(histogram.get(s, 0) >= 1 for s in ALLOWED_DOSSIER_STATUSES)
