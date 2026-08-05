"""Aggregate FOUNDER R1 findings into the required return matrix."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_findings(
    *,
    pass_number: int,
    authority: dict[str, Any],
    vocabulary: dict[str, Any],
    adversarial: dict[str, Any],
) -> dict[str, Any]:
    critical: list[dict[str, Any]] = []
    high: list[dict[str, Any]] = []

    for c in authority.get("authority_conflicts") or []:
        item = {
            "source": "authority_scan",
            "id": c.get("id"),
            "detail": c.get("detail"),
            "domain": c.get("domain"),
            "severity": c.get("severity", "high"),
        }
        if item["severity"] == "critical":
            critical.append(item)
        else:
            high.append(item)

    for m in vocabulary.get("mismatches") or []:
        item = {
            "source": "vocabulary",
            "id": m.get("id"),
            "detail": m.get("detail"),
            "severity": m.get("severity", "high"),
        }
        if item["severity"] == "critical":
            critical.append(item)
        else:
            high.append(item)

    for s in adversarial.get("scenarios") or []:
        if s.get("severity") in {"critical", "high"} and (
            s.get("false_pass") or not s.get("cross_lane_invariant_enforced")
        ):
            # Only elevate when the scenario exposes a real gap.
            if s.get("false_pass") or (
                s.get("expected_fail_closed") and not s.get("observed_fail_closed")
            ):
                item = {
                    "source": "adversarial",
                    "id": s.get("scenario_id"),
                    "detail": s.get("detail"),
                    "severity": s.get("severity"),
                    "false_pass": s.get("false_pass"),
                    "missing_negative_test": s.get("missing_negative_test"),
                }
                if s.get("severity") == "critical":
                    critical.append(item)
                else:
                    high.append(item)

    # Deduplicate by id preserving order.
    def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for it in items:
            key = str(it.get("id"))
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    critical = _dedupe(critical)
    high = _dedupe(high)

    false_pass_count = int(adversarial.get("false_PASS_count") or 0)
    authority_conflict_count = int(authority.get("authority_conflict_count") or 0)
    missing_negative_test_count = int(adversarial.get("missing_negative_test_count") or 0)

    # Integration recommendation: block if any critical remains.
    if critical:
        integration_recommendation = "BLOCK_INTEGRATION_CRITICAL_CROSS_LANE_GAPS"
    elif high and false_pass_count > 0:
        integration_recommendation = "HOLD_FOR_REMEDIATION_HIGH_FINDINGS"
    else:
        integration_recommendation = "CONDITIONAL_INTEGRATE_WITH_BRIDGE_GATE"

    return {
        "schema": "v11_review_decision_execution_findings",
        "pass_number": pass_number,
        "created_at": _utc(),
        "false_PASS_count": false_pass_count,
        "authority_conflict_count": authority_conflict_count,
        "missing_negative_test_count": missing_negative_test_count,
        "critical_findings": critical,
        "high_findings": high,
        "critical_count": len(critical),
        "high_count": len(high),
        "integration_recommendation": integration_recommendation,
        "vocabulary_mismatch_count": int(vocabulary.get("mismatch_count") or 0),
        "scenario_count": int(adversarial.get("scenario_count") or 0),
    }
