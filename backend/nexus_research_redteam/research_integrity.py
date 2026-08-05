"""Research integrity oracles — fail-closed detectors for false-pass attacks.

These seals live in the red-team owned package. They encode the invariants that
research readiness must not treat as PASS: future leakage, OOS consumption,
fabricated universes, inflated counters, cherry-picked results, relabeled
candidates, omitted costs, fixtures claimed as real, and provider transport
failures mislabeled as AI quality failures.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


CONTROL_FIXTURE_LABEL = "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
REAL_PERFORMANCE_LABEL = "REAL_HISTORICAL_MARKET_PERFORMANCE"


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def seal_research_result(result: dict[str, Any]) -> dict[str, Any]:
    """Bind a research result envelope for tamper detection."""
    required = (
        "result_id",
        "candidate_ids",
        "universe_members",
        "as_of_ms",
        "counters",
        "metrics",
        "cost_model_version",
        "cost_summary",
        "fixture_label",
        "provider_status",
    )
    missing = [k for k in required if k not in result]
    if missing:
        return {
            "ok": False,
            "status": "RESULT_MISSING_KEYS",
            "missing": missing,
            "seal": None,
        }
    body = {k: result[k] for k in required}
    return {"ok": True, "status": "SEALED", "missing": [], "seal": _sha(body), "body": body}


def verify_research_result_seal(result: dict[str, Any], expected_seal: str) -> dict[str, Any]:
    sealed = seal_research_result(result)
    if not sealed.get("ok"):
        return {"ok": False, "status": sealed.get("status"), "detail": sealed}
    actual = sealed["seal"]
    if actual != expected_seal:
        return {
            "ok": False,
            "status": "RESULT_SEAL_MISMATCH",
            "expected": expected_seal,
            "actual": actual,
        }
    return {"ok": True, "status": "PASS", "seal": actual}


def detect_fabricated_universe(
    *,
    claimed_members: list[str],
    pit_members: list[str],
) -> dict[str, Any]:
    """Any claimed member absent from PIT reconstruction is fabricated."""
    claimed = sorted(set(claimed_members))
    pit = sorted(set(pit_members))
    fabricated = sorted(set(claimed) - set(pit))
    return {
        "ok": len(fabricated) == 0 and claimed == pit,
        "status": "FABRICATED_UNIVERSE" if fabricated else "PASS",
        "fabricated": fabricated,
        "claimed": claimed,
        "pit_members": pit,
    }


def detect_counter_inflation(
    *,
    reported_counters: dict[str, int],
    sealed_event_counts: dict[str, int],
) -> dict[str, Any]:
    """Reported counters must not exceed sealed event counts for any key."""
    inflated: dict[str, dict[str, int]] = {}
    for key, sealed in sealed_event_counts.items():
        reported = int(reported_counters.get(key, 0))
        if reported > int(sealed):
            inflated[key] = {"reported": reported, "sealed": int(sealed)}
    # Also: inventing counters that have zero sealed events.
    for key, reported in reported_counters.items():
        if key not in sealed_event_counts and int(reported) > 0:
            inflated[key] = {"reported": int(reported), "sealed": 0}
    return {
        "ok": len(inflated) == 0,
        "status": "COUNTER_INFLATION" if inflated else "PASS",
        "inflated": inflated,
    }


def detect_result_cherry_picking(
    *,
    full_population_ids: list[str],
    reported_ids: list[str],
    full_metric: float,
    reported_metric: float,
    disclosed_subset: bool,
) -> dict[str, Any]:
    """Subset with improved metric without disclosure is cherry-picking."""
    full_set = set(full_population_ids)
    reported_set = set(reported_ids)
    is_subset = reported_set.issubset(full_set) and reported_set != full_set
    improved = reported_metric > full_metric
    cherry = is_subset and improved and not disclosed_subset
    return {
        "ok": not cherry,
        "status": "RESULT_CHERRY_PICKING" if cherry else "PASS",
        "is_subset": is_subset,
        "improved": improved,
        "disclosed_subset": disclosed_subset,
        "full_metric": full_metric,
        "reported_metric": reported_metric,
    }


def detect_candidate_relabeling(
    *,
    sealed_labels: dict[str, str],
    reported_labels: dict[str, str],
) -> dict[str, Any]:
    """Candidate identity remapping after seal is relabeling."""
    remapped: dict[str, dict[str, str]] = {}
    for cid, sealed_label in sealed_labels.items():
        reported = reported_labels.get(cid)
        if reported is None:
            remapped[cid] = {"sealed": sealed_label, "reported": "<missing>"}
        elif reported != sealed_label:
            remapped[cid] = {"sealed": sealed_label, "reported": reported}
    # Swap attack: values permute across ids.
    if sorted(sealed_labels.values()) == sorted(reported_labels.values()) and sealed_labels != reported_labels:
        for cid in sealed_labels:
            if sealed_labels[cid] != reported_labels.get(cid):
                remapped[cid] = {
                    "sealed": sealed_labels[cid],
                    "reported": str(reported_labels.get(cid)),
                }
    return {
        "ok": len(remapped) == 0,
        "status": "CANDIDATE_RELABELING" if remapped else "PASS",
        "remapped": remapped,
    }


def detect_cost_omission(result: dict[str, Any]) -> dict[str, Any]:
    """Research result without cost version + summary is cost omission."""
    missing: list[str] = []
    cost_version = result.get("cost_model_version")
    cost_summary = result.get("cost_summary")
    if not cost_version:
        missing.append("cost_model_version")
    if not isinstance(cost_summary, dict) or not cost_summary:
        missing.append("cost_summary")
    elif "total_cost" not in cost_summary:
        missing.append("cost_summary.total_cost")
    # Zero-cost claim with missing breakdown is also omission.
    if isinstance(cost_summary, dict) and cost_summary.get("total_cost") is None:
        missing.append("cost_summary.total_cost_null")
    return {
        "ok": len(missing) == 0,
        "status": "COST_OMISSION" if missing else "PASS",
        "missing": missing,
    }


def detect_fixture_as_real(result: dict[str, Any]) -> dict[str, Any]:
    """Control fixtures must never be labeled as real market performance."""
    label = str(result.get("fixture_label") or "")
    claims_real = bool(result.get("claims_real_performance"))
    is_control = label == CONTROL_FIXTURE_LABEL or bool(result.get("is_control_fixture"))
    hole = is_control and (claims_real or label == REAL_PERFORMANCE_LABEL)
    return {
        "ok": not hole,
        "status": "FIXTURE_AS_REAL" if hole else "PASS",
        "fixture_label": label,
        "claims_real_performance": claims_real,
        "is_control_fixture": is_control,
    }


def detect_provider_failure_as_quality(
    provider_status: str,
    *,
    claimed_as_quality: bool | None = None,
) -> dict[str, Any]:
    """Transport / quota / circuit failures must not be classified as AI quality."""
    from backend.nexus_edge_discovery.provider_transport_v23 import (
        is_ai_quality_failure,
        is_transport_failure,
    )

    status = str(provider_status or "")
    transport = is_transport_failure(status)
    quality = is_ai_quality_failure(status)
    # Canonical classifiers must never mark transport as quality.
    classifier_hole = transport and quality
    # Explicit attacker claim that a transport failure is "quality".
    claim_hole = bool(claimed_as_quality) and transport
    ok = (not classifier_hole) and (not claim_hole)
    return {
        "ok": ok,
        "status": "PASS" if ok else "PROVIDER_FAILURE_AS_QUALITY",
        "provider_status": status,
        "is_transport_failure": transport,
        "is_ai_quality_failure": quality,
        "claimed_as_quality": claimed_as_quality,
    }


def classify_provider_status(provider_status: str) -> dict[str, Any]:
    """Return canonical classification used by readiness gates."""
    from backend.nexus_edge_discovery.provider_transport_v23 import (
        is_ai_quality_failure,
        is_transport_failure,
    )

    status = str(provider_status or "")
    transport = is_transport_failure(status)
    quality = is_ai_quality_failure(status)
    if transport and quality:
        bucket = "MISLABELED_TRANSPORT_AS_QUALITY"
        ok = False
    elif transport:
        bucket = "TRANSPORT_FAILURE"
        ok = True
    elif quality:
        bucket = "AI_QUALITY_FAILURE"
        ok = True
    else:
        bucket = "OTHER_OR_OK"
        ok = True
    return {
        "ok": ok,
        "bucket": bucket,
        "provider_status": status,
        "is_transport_failure": transport,
        "is_ai_quality_failure": quality,
    }
