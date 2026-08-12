"""Adversarial review probes for V15-H risk/capacity engine (Pass 2)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_risk_capacity.ai_gate import apply_ai_suggestion
from backend.nexus_risk_capacity.constants import (
    ALLOWED_LABELS,
    ARTIFACT_DIRNAME,
    BANNED_CLAIM_FRAGMENTS,
    CANONICAL_COST_AUTHORITY,
    HARD_BANS,
    REQUIRED_COST_COMPONENTS,
    REQUIRED_OUTPUT_KEYS,
    REVIEW_DIMENSIONS,
)
from backend.nexus_risk_capacity.engine import run_risk_capacity_review
from backend.nexus_risk_capacity.metrics import analyze_candidate, deterministic_fingerprint
from backend.nexus_risk_capacity.fixtures import build_synthetic_candidates


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
    """Fail-closed checks for bans, labels, AI override, and dimension coverage."""
    report = report or run_risk_capacity_review(pass_id=2)
    findings: list[dict[str, str]] = []

    dims = set(report.get("review_dimensions") or [])
    findings.append(
        _finding(
            "ADV_DIMENSION_COVERAGE",
            severity="CRITICAL",
            status="PASS" if dims == set(REVIEW_DIMENSIONS) else "REMAINING",
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
            detail="expectancy, capacity, concentrations, drawdown, liquidation, data quality, fingerprint",
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

    promo_ok = (
        int(report.get("strategy_promoted_count") or 0) == 0
        and int(report.get("strategy_selected_count") or 0) == 0
        and all(
            c.get("strategy_promoted") is False and c.get("strategy_selected") is False
            for c in report.get("candidates") or []
        )
    )
    findings.append(
        _finding(
            "ADV_NO_STRATEGY_PROMOTION",
            severity="CRITICAL",
            status="PASS" if promo_ok else "REMAINING",
            detail="strategy_promoted_count=0; strategy_selected_count=0",
        )
    )

    ai_ok = (
        int(report.get("ai_override_applied_count") or 0) == 0
        and all(c.get("ai_override_applied") is False for c in report.get("candidates") or [])
        and int(report.get("ai_override_attempted_count") or 0)
        == len(report.get("candidates") or [])
    )
    findings.append(
        _finding(
            "ADV_AI_CANNOT_OVERRIDE",
            severity="CRITICAL",
            status="PASS" if ai_ok else "REMAINING",
            detail=(
                f"applied={report.get('ai_override_applied_count')} "
                f"attempted={report.get('ai_override_attempted_count')}"
            ),
        )
    )

    # Fingerprint stability: re-analyze first candidate; fingerprint must match.
    cands = build_synthetic_candidates()
    first = analyze_candidate(cands[0])
    reported_fp = next(
        (
            c.get("deterministic_fingerprint")
            for c in report.get("candidates") or []
            if c.get("candidate_id") == cands[0].candidate_id
        ),
        None,
    )
    # Recompute fingerprint the same way analyze_candidate does for the public keys.
    fp_ok = reported_fp == first["deterministic_fingerprint"] and bool(reported_fp)
    # AI suggestion must not change fingerprint-bearing fields.
    mutated = apply_ai_suggestion(
        {"candidate_id": "X", "label": "RISK_CAPACITY_OBSERVED", "net_expectancy": "1"},
        {"label": "QUALIFIED", "net_expectancy": "999"},
    )
    fp_ok = fp_ok and mutated["label"] == "RISK_CAPACITY_OBSERVED"
    findings.append(
        _finding(
            "ADV_DETERMINISTIC_FINGERPRINT",
            severity="CRITICAL",
            status="PASS" if fp_ok else "REMAINING",
            detail=f"fingerprint_match={reported_fp == first['deterministic_fingerprint']}",
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
        and report.get("status_json_written") is False
        and set(HARD_BANS).issubset(set(report.get("hard_bans") or []))
        and bool((report.get("hard_ban_probes") or {}).get("all_refused"))
    )
    findings.append(
        _finding(
            "ADV_HARD_BAN_COMPLIANCE",
            severity="CRITICAL",
            status="PASS" if bans_ok else "REMAINING",
            detail="oos/wf/demo/shadow/exchange/profitability/qualified/pr27/ai/status-json bans held",
        )
    )

    hist = report.get("label_histogram") or {}
    neg_ok = (
        int(hist.get("INSUFFICIENT_SAMPLE", 0)) >= 1
        or int(hist.get("DATA_QUALITY_BLOCKED", 0)) >= 1
    ) and (
        int(hist.get("COST_DESTROYED", 0))
        + int(hist.get("FRAGILE_TO_EXECUTION", 0))
        + int(hist.get("CAPACITY_LIMITED", 0))
        + int(hist.get("CONCENTRATION_BLOCKED", 0))
        + int(hist.get("DRAWDOWN_ASSUMPTION_UNSAFE", 0))
        + int(hist.get("LIQUIDATION_DISTANCE_UNSAFE", 0))
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

    # No *_status.json under owned artifact dirname.
    artifact_root = (
        Path(__file__).resolve().parents[2]
        / "artifacts"
        / "readiness"
        / "immutable"
        / ARTIFACT_DIRNAME
    )
    status_json_files = (
        list(artifact_root.glob("*_status.json")) + list(artifact_root.glob("status.json"))
        if artifact_root.exists()
        else []
    )
    # Also reject any accidental runtime-style names in report paths later; here check flag.
    no_status = report.get("status_json_written") is False and len(status_json_files) == 0
    findings.append(
        _finding(
            "ADV_NO_STATUS_JSON",
            severity="CRITICAL",
            status="PASS" if no_status else "REMAINING",
            detail=f"status_json_files={[p.name for p in status_json_files]}",
        )
    )

    # False-PASS: banned claim fragments must never appear in labels/status.
    claim_hits: list[str] = []
    for c in report.get("candidates") or []:
        blob = f"{c.get('label')}|{c.get('status')}"
        upper = blob.upper()
        for frag in BANNED_CLAIM_FRAGMENTS:
            if frag in upper:
                claim_hits.append(f"{c.get('candidate_id')}:{frag}")
    findings.append(
        _finding(
            "ADV_NO_BANNED_CLAIM_FRAGMENTS",
            severity="CRITICAL",
            status="PASS" if not claim_hits else "REMAINING",
            detail="none" if not claim_hits else ",".join(claim_hits),
        )
    )

    # False-PASS: structural data-quality fixtures must not be concealed as observed.
    dq_labels = {
        c["candidate_id"]: c["label"]
        for c in report.get("candidates") or []
        if c.get("missing_data") or c.get("stale_data")
    }
    dq_ok = all(lbl == "DATA_QUALITY_BLOCKED" for lbl in dq_labels.values()) and len(dq_labels) >= 1
    findings.append(
        _finding(
            "ADV_NO_STALE_DATA_CONCEALMENT",
            severity="CRITICAL",
            status="PASS" if dq_ok else "REMAINING",
            detail=f"data_quality_candidates={dq_labels}",
        )
    )

    # Schema drift: every required review dimension must appear in dimension_summaries.
    schema_ok = True
    for c in report.get("candidates") or []:
        summaries = set((c.get("dimension_summaries") or {}).keys())
        if summaries != set(REVIEW_DIMENSIONS):
            schema_ok = False
            break
    findings.append(
        _finding(
            "ADV_NO_SCHEMA_DRIFT",
            severity="CRITICAL",
            status="PASS" if schema_ok else "REMAINING",
            detail="every candidate dimension_summaries covers REVIEW_DIMENSIONS",
        )
    )

    remaining = [f for f in findings if f["status"] == "REMAINING"]
    critical_remaining = [f for f in remaining if f["severity"] == "CRITICAL"]
    return {
        "schema": "FOUNDER_V15_H_ADVERSARIAL_REVIEW",
        "pass_ok": len(critical_remaining) == 0 and len(remaining) == 0,
        "remaining_count": len(remaining),
        "critical_remaining_count": len(critical_remaining),
        "findings": findings,
        "qualification_ready_count": qrc,
        "strategy_promoted_count": 0,
        "ai_override_applied_count": int(report.get("ai_override_applied_count") or 0),
        "hard_ban_count": len(HARD_BANS),
        "deterministic_fingerprint_probe": deterministic_fingerprint(
            {"lane": "V15-H", "seed": report.get("random_seed")}
        ),
    }
