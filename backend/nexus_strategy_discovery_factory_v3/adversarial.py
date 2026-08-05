"""Adversarial review probes for V13-C discovery factory (Pass 2)."""
from __future__ import annotations

from typing import Any

from backend.nexus_strategy_discovery_factory_v3.constants import (
    ALLOWED_LABELS,
    HARD_BANS,
    MECHANISM_FAMILIES,
    REQUIRED_COST_COMPONENTS,
)
from backend.nexus_strategy_discovery_factory_v3.factory import run_discovery_factory


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
    """Two-pass adversarial checks — fail closed on ban / label / cost gaps."""
    report = report or run_discovery_factory(pass_id=2)
    findings: list[dict[str, str]] = []

    fams = [c["family_id"] for c in report["candidates"]]
    mechs = [c["semantic_mechanism_id"] for c in report["candidates"]]
    if len(set(fams)) == len(MECHANISM_FAMILIES) and len(set(mechs)) == len(mechs):
        findings.append(
            _finding(
                "ADV_FAMILY_DISTINCT",
                severity="HIGH",
                status="PASS",
                detail="all mechanism families present with unique semantic IDs",
            )
        )
    else:
        findings.append(
            _finding(
                "ADV_FAMILY_DISTINCT",
                severity="CRITICAL",
                status="REMAINING",
                detail="duplicate or missing mechanism families",
            )
        )

    cost_ok = True
    for c in report["candidates"]:
        comps = c.get("cost_components") or {}
        for key in REQUIRED_COST_COMPONENTS:
            if key not in comps:
                cost_ok = False
                break
        if not cost_ok:
            break
    findings.append(
        _finding(
            "ADV_FULL_COST_COMPONENTS",
            severity="CRITICAL",
            status="PASS" if cost_ok else "REMAINING",
            detail=(
                "entry/exit fee, spread, slippage, funding, partial fill, "
                "cancel-replace, market impact"
            ),
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
        and int(report.get("exchange_write_attempt_count") or 0) == 0
        and report.get("profitability_claimed") is False
        and report.get("qualified_claimed") is False
        and report.get("pr27_merge_attempted") is False
    )
    findings.append(
        _finding(
            "ADV_HARD_BAN_COMPLIANCE",
            severity="CRITICAL",
            status="PASS" if bans_ok else "REMAINING",
            detail="oos/wf/demo/exchange/profitability/qualified/pr27 bans held",
        )
    )

    configs = int(report.get("candidate_configuration_count") or 0)
    findings.append(
        _finding(
            "ADV_NO_COSMETIC_FLOOD",
            severity="HIGH",
            status="PASS" if configs == len(MECHANISM_FAMILIES) else "REMAINING",
            detail=f"candidate_configuration_count={configs}",
        )
    )

    pit_ok = all(
        (c.get("point_in_time_proof") or {}).get("lookahead_forbidden") is True
        and int((c.get("point_in_time_proof") or {}).get("future_bar_reference_count") or 0)
        == 0
        for c in report["candidates"]
    )
    findings.append(
        _finding(
            "ADV_PIT_PROOF",
            severity="HIGH",
            status="PASS" if pit_ok else "REMAINING",
            detail="lookahead forbidden and future-bar refs zero",
        )
    )

    promising = [
        c
        for c in report["candidates"]
        if c.get("label") == "DEVELOPMENT_PROMISING_NOT_QUALIFIED"
    ]
    promising_safe = all(
        c.get("qualified") is False and c.get("qualification_ready") is False
        for c in promising
    )
    findings.append(
        _finding(
            "ADV_PROMISING_NOT_QUALIFIED",
            severity="CRITICAL",
            status="PASS" if promising_safe else "FIXED",
            detail="DEVELOPMENT_PROMISING_NOT_QUALIFIED never sets qualified flags",
        )
    )

    remaining = [f for f in findings if f["status"] == "REMAINING"]
    return {
        "schema": "v13_c_strategy_discovery_adversarial_v1",
        "pass": "pass_2",
        "finding_count": len(findings),
        "remaining_count": len(remaining),
        "pass_ok": len(remaining) == 0,
        "hard_bans_checked": sorted(HARD_BANS),
        "findings": findings,
        "qualification_ready_count": qrc,
    }
