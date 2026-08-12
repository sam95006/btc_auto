"""Three-pass adversarial review for V16-E Lesson Compiler."""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_compiler.campaign import run_compiler_campaign
from backend.nexus_lesson_compiler.constants import (
    BANNED_CLAIM_FRAGMENTS,
    EXPECTED_FIXTURE_COUNT,
    HARD_BANS,
    LESSON_STATUS_CANDIDATE,
    MIN_LESSON_COUNT,
    REQUIRED_LESSON_FIELDS,
)


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
        "status": status,
        "detail": detail,
    }


def run_adversarial_review(
    report: dict[str, Any] | None = None,
    *,
    pass_name: str = "pass_3",
) -> dict[str, Any]:
    report = report or run_compiler_campaign(pass_id=3)
    findings: list[dict[str, str]] = []

    count = int(report.get("lesson_count") or 0)
    findings.append(
        _finding(
            "ADV_LESSON_COUNT",
            severity="CRITICAL",
            status="PASS"
            if count >= MIN_LESSON_COUNT and count == EXPECTED_FIXTURE_COUNT
            else "REMAINING",
            detail=f"lesson_count={count} expected={EXPECTED_FIXTURE_COUNT}",
        )
    )

    ids = [e["lesson_id"] for e in report["lessons"]]
    digests = [e["compile_digest"] for e in report["lessons"]]
    distinct_ok = len(ids) == len(set(ids)) and len(digests) == len(set(digests)) and len(ids) == count
    findings.append(
        _finding(
            "ADV_DISTINCT_LESSONS",
            severity="CRITICAL",
            status="PASS" if distinct_ok else "REMAINING",
            detail="unique lesson ids and compile digests",
        )
    )

    fields_ok = True
    for e in report["lessons"]:
        for field in REQUIRED_LESSON_FIELDS:
            if field not in e:
                fields_ok = False
                break
            val = e[field]
            if field == "contradictory_evidence":
                if val is None:
                    fields_ok = False
            elif val in (None, "", {}, []):
                fields_ok = False
        if not fields_ok:
            break
        if not e.get("conditions"):
            fields_ok = False
        if not e.get("then_action"):
            fields_ok = False
    findings.append(
        _finding(
            "ADV_REQUIRED_SCHEMA_FIELDS",
            severity="CRITICAL",
            status="PASS" if fields_ok else "REMAINING",
            detail="conditions/scope/expert/regimes/expiry/evidence/confidence/contradictory/author",
        )
    )

    candidate_ok = all(
        e.get("status") == LESSON_STATUS_CANDIDATE and e.get("active") is False
        for e in report["lessons"]
    ) and int(report.get("active_lesson_count") or 0) == 0
    findings.append(
        _finding(
            "ADV_CANDIDATE_ONLY",
            severity="CRITICAL",
            status="PASS" if candidate_ok else "REMAINING",
            detail="all lessons CANDIDATE; active_lesson_count=0",
        )
    )

    mutation_ok = (
        report.get("production_risk_mutated") is False
        and report.get("production_leverage_mutated") is False
        and all(
            e.get("mutates_production_risk") is False
            and e.get("mutates_production_leverage") is False
            for e in report["lessons"]
        )
    )
    findings.append(
        _finding(
            "ADV_NO_PRODUCTION_RISK_LEVERAGE",
            severity="CRITICAL",
            status="PASS" if mutation_ok else "REMAINING",
            detail="no production risk/leverage mutation flags",
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

    claim_ok = (
        report.get("edge_claimed") is False
        and report.get("profitability_claimed") is False
        and report.get("qualified_claimed") is False
        and int(report.get("edge_claim_count") or 0) == 0
        and int(report.get("profitability_claim_count") or 0) == 0
        and all(
            e.get("edge_claimed") is False
            and e.get("profitability_claimed") is False
            and e.get("qualified") is False
            and e.get("qualification_ready") is False
            for e in report["lessons"]
        )
    )
    findings.append(
        _finding(
            "ADV_NO_EDGE_OR_QUALIFICATION_CLAIMS",
            severity="CRITICAL",
            status="PASS" if claim_ok else "REMAINING",
            detail="no edge/profitability/qualification claims",
        )
    )

    bans_ok = (
        report.get("formal_walk_forward_executed") is False
        and report.get("oos_executed") is False
        and report.get("oos_consumed") is False
        and int(report.get("demo_order_count") or 0) == 0
        and int(report.get("shadow_order_count") or 0) == 0
        and int(report.get("exchange_write_attempt_count") or 0) == 0
        and int(report.get("mainnet_touch_count") or 0) == 0
        and report.get("pr26_merge_attempted") is False
        and report.get("pr27_merge_attempted") is False
        and report.get("auto_integrate_attempted") is False
        and report.get("private_core_deploy_attempted") is False
        and set(HARD_BANS).issubset(set(report.get("hard_bans") or []))
    )
    findings.append(
        _finding(
            "ADV_HARD_BAN_COMPLIANCE",
            severity="CRITICAL",
            status="PASS" if bans_ok else "REMAINING",
            detail="oos/wf/demo/shadow/exchange/mainnet/pr26/pr27/auto-integrate/deploy bans held",
        )
    )

    replay_ok = bool(report.get("replay_stable")) and bool(report.get("campaign_digest"))
    findings.append(
        _finding(
            "ADV_DETERMINISTIC_DIGEST",
            severity="CRITICAL",
            status="PASS" if replay_ok else "REMAINING",
            detail=f"campaign_digest={(report.get('campaign_digest') or '')[:16]}",
        )
    )

    vocab_ok = True
    for e in report["lessons"]:
        label = str(e.get("label") or "").upper()
        status = str(e.get("status") or "").upper()
        for frag in BANNED_CLAIM_FRAGMENTS:
            if frag in label or frag in status:
                vocab_ok = False
    findings.append(
        _finding(
            "ADV_BANNED_VOCAB",
            severity="CRITICAL",
            status="PASS" if vocab_ok else "REMAINING",
            detail="banned profitability/ACTIVE vocabulary absent",
        )
    )

    no_status = report.get("status_json_written") is False
    findings.append(
        _finding(
            "ADV_NO_STATUS_JSON",
            severity="HIGH",
            status="PASS" if no_status else "REMAINING",
            detail="lane must not write *_status.json report files",
        )
    )

    remaining = [f for f in findings if f["status"] == "REMAINING"]
    critical_remaining = [f for f in remaining if f["severity"] == "CRITICAL"]
    high_remaining = [f for f in remaining if f["severity"] == "HIGH"]
    return {
        "schema": "v16_e_lesson_compiler_adversarial_v1",
        "pass": pass_name,
        "finding_count": len(findings),
        "remaining_count": len(remaining),
        "critical_remaining": len(critical_remaining),
        "high_remaining": len(high_remaining),
        "pass_ok": len(remaining) == 0,
        "hard_bans_checked": sorted(HARD_BANS),
        "findings": findings,
        "qualification_ready_count": qrc,
        "lesson_count": count,
        "active_lesson_count": int(report.get("active_lesson_count") or 0),
        "campaign_digest": report.get("campaign_digest"),
    }
