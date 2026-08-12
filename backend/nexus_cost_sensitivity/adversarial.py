"""Adversarial review probes for V14-E cost sensitivity lab (Pass 2)."""
from __future__ import annotations

from typing import Any

from backend.nexus_cost_sensitivity.constants import (
    ALLOWED_LABELS,
    CANONICAL_COST_AUTHORITY,
    HARD_BANS,
    REQUIRED_COST_COMPONENTS,
    REQUIRED_OUTPUT_KEYS,
    SENSITIVITY_DIMENSIONS,
)
from backend.nexus_cost_sensitivity.lab import run_cost_sensitivity_lab


def _finding(
    finding_id: str,
    *,
    severity: str,
    status: str,
    detail: str,
) -> dict[str, str]:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "status": status,  # PASS | FIXED | REMAINING
        "detail": detail,
    }


def run_adversarial_review(report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fail-closed checks for bans, labels, cost authority, and coverage."""
    report = report or run_cost_sensitivity_lab(pass_id=2)
    findings: list[dict[str, str]] = []

    dims = set(report.get("sensitivity_dimensions") or [])
    findings.append(
        _finding(
            "ADV_DIMENSION_COVERAGE",
            severity="CRITICAL",
            status="PASS" if dims == set(SENSITIVITY_DIMENSIONS) else "REMAINING",
            detail=f"dimensions={sorted(dims)}",
        )
    )

    cost_ok = True
    output_ok = True
    authority_ok = True
    for c in report.get("candidates") or []:
        comps = c.get("cost_components") or {}
        for key in REQUIRED_COST_COMPONENTS:
            if key not in comps:
                cost_ok = False
        for key in REQUIRED_OUTPUT_KEYS:
            if key not in c:
                output_ok = False
        if c.get("cost_authority") != CANONICAL_COST_AUTHORITY:
            authority_ok = False
        if c.get("canonical_cost_formula_mutated") is True:
            authority_ok = False
    findings.append(
        _finding(
            "ADV_FULL_COST_COMPONENTS",
            severity="CRITICAL",
            status="PASS" if cost_ok else "REMAINING",
            detail="all required cost components present on every candidate",
        )
    )
    findings.append(
        _finding(
            "ADV_REQUIRED_OUTPUTS",
            severity="CRITICAL",
            status="PASS" if output_ok else "REMAINING",
            detail="gross/net expectancy, break-even, max spread/slip, capacity, fragility",
        )
    )
    findings.append(
        _finding(
            "ADV_CANONICAL_COST_AUTHORITY",
            severity="CRITICAL",
            status="PASS" if authority_ok else "REMAINING",
            detail=f"authority={CANONICAL_COST_AUTHORITY}; formula_mutated=false",
        )
    )

    bad_labels = [
        c["label"] for c in report["candidates"] if c.get("label") not in ALLOWED_LABELS
    ]
    findings.append(
        _finding(
            "ADV_LABEL_ALLOWLIST",
            severity="CRITICAL",
            status="PASS" if not bad_labels else "REMAINING",
            detail=(
                "illegal_labels=" + ",".join(bad_labels)
                if bad_labels
                else "all labels allowed"
            ),
        )
    )

    qrc = int(report.get("qualification_ready_count", -1))
    findings.append(
        _finding(
            "ADV_QUALIFICATION_READY_ZERO",
            severity="CRITICAL",
            status="PASS" if qrc == 0 else "REMAINING",
            detail=f"qualification_ready_count={qrc}",
        )
    )

    bans_ok = (
        report.get("formal_walk_forward_executed") is False
        and report.get("oos_executed") is False
        and report.get("oos_consumed") is False
        and int(report.get("demo_order_count") or 0) == 0
        and int(report.get("shadow_order_count") or 0) == 0
        and int(report.get("exchange_write_attempt_count") or 0) == 0
        and int(report.get("mainnet_client_created_count") or 0) == 0
        and report.get("profitability_claimed") is False
        and report.get("qualified_claimed") is False
        and report.get("pr27_merge_attempted") is False
        and report.get("auto_integrate_attempted") is False
        and report.get("canonical_cost_formula_mutated") is False
        and set(HARD_BANS).issubset(set(report.get("hard_bans") or []))
    )
    findings.append(
        _finding(
            "ADV_HARD_BAN_COMPLIANCE",
            severity="CRITICAL",
            status="PASS" if bans_ok else "REMAINING",
            detail="oos/wf/demo/shadow/exchange/profitability/qualified/pr27/auto-integrate bans held",
        )
    )

    # Negative-path coverage: at least one insufficient / data-quality / cost-destroyed.
    hist = report.get("label_histogram") or {}
    neg_ok = (
        int(hist.get("INSUFFICIENT_SAMPLE", 0)) >= 1
        or int(hist.get("DATA_QUALITY_BLOCKED", 0)) >= 1
    ) and (
        int(hist.get("COST_DESTROYED", 0))
        + int(hist.get("FRAGILE_TO_EXECUTION", 0))
        + int(hist.get("CAPACITY_LIMITED", 0))
        >= 1
    )
    findings.append(
        _finding(
            "ADV_NEGATIVE_PATH_COVERAGE",
            severity="HIGH",
            status="PASS" if neg_ok else "REMAINING",
            detail=f"label_histogram={hist}",
        )
    )

    # Fixture-only claim trap: evidence_class must declare synthetic development.
    fixture_ok = all(
        c.get("evidence_class") == "FIXTURE_SYNTHETIC_DEVELOPMENT_ONLY"
        and c.get("data_lineage") == "SYNTHETIC_DEVELOPMENT_FIXTURE"
        and c.get("oos_consumed") is False
        for c in report.get("candidates") or []
    )
    findings.append(
        _finding(
            "ADV_NO_FIXTURE_AS_LIVE_EDGE",
            severity="CRITICAL",
            status="PASS" if fixture_ok else "REMAINING",
            detail="all candidates declare synthetic development evidence class",
        )
    )

    # Silent fallback trap: every candidate must verify CostBridge + impact labeling.
    bridge_ok = all(
        (c.get("baseline") or {}).get("cost_bridge_verified") is True
        and (c.get("baseline") or {}).get("market_impact_outside_cost_bridge") is True
        for c in report.get("candidates") or []
    )
    findings.append(
        _finding(
            "ADV_NO_SILENT_COST_FALLBACK",
            severity="CRITICAL",
            status="PASS" if bridge_ok else "REMAINING",
            detail="CostBridge verified; market impact explicitly outside bridge",
        )
    )

    remaining = [f for f in findings if f["status"] == "REMAINING"]
    critical_remaining = [f for f in remaining if f["severity"] == "CRITICAL"]
    return {
        "schema": "FOUNDER_V14_E_ADVERSARIAL_REVIEW",
        "pass_ok": len(critical_remaining) == 0 and len(remaining) == 0,
        "remaining_count": len(remaining),
        "critical_remaining_count": len(critical_remaining),
        "findings": findings,
        "qualification_ready_count": qrc,
        "hard_ban_count": len(HARD_BANS),
    }
