"""Two-pass adversarial review for V15-B Mechanism Execution Compiler."""
from __future__ import annotations

from typing import Any

from backend.nexus_mechanism_execution_compiler.campaign import run_compiler_campaign
from backend.nexus_mechanism_execution_compiler.constants import (
    ALLOWED_LABELS,
    BANNED_CLAIM_FRAGMENTS,
    EXPECTED_MECHANISM_COUNT,
    HARD_BANS,
    MIN_EXECUTOR_COUNT,
    REQUIRED_EXECUTOR_FIELDS,
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
    pass_name: str = "pass_2",
) -> dict[str, Any]:
    report = report or run_compiler_campaign(pass_id=2)
    findings: list[dict[str, str]] = []

    count = int(report.get("mechanism_executor_count") or 0)
    findings.append(
        _finding(
            "ADV_EXECUTOR_COUNT_42",
            severity="CRITICAL",
            status="PASS"
            if count >= MIN_EXECUTOR_COUNT and count == EXPECTED_MECHANISM_COUNT
            else "REMAINING",
            detail=f"mechanism_executor_count={count} expected={EXPECTED_MECHANISM_COUNT}",
        )
    )

    ids = [e["executor_id"] for e in report["executors"]]
    mechs = [e["mechanism_id"] for e in report["executors"]]
    kinds = [
        (
            (e.get("signal_contract") or {}).get("signal_kind"),
            (e.get("feature_contract") or {}).get("primary_feature"),
            (e.get("feature_contract") or {}).get("secondary_feature"),
            (e.get("signal_contract") or {}).get("direction_mode"),
        )
        for e in report["executors"]
    ]
    rationales = [e.get("economic_rationale") for e in report["executors"]]
    distinct_ok = (
        len(ids) == len(set(ids))
        and len(mechs) == len(set(mechs))
        and len(kinds) == len(set(kinds))
        and len(rationales) == len(set(rationales))
        and len(ids) == count
    )
    findings.append(
        _finding(
            "ADV_NO_PARAM_COLLAPSE",
            severity="CRITICAL",
            status="PASS" if distinct_ok else "REMAINING",
            detail="unique executor ids, mechanism ids, signal contracts, rationales",
        )
    )

    fields_ok = True
    for e in report["executors"]:
        for field in REQUIRED_EXECUTOR_FIELDS:
            if field not in e or e[field] in (None, "", [], {}):
                fields_ok = False
                break
        link = e.get("economic_rationale_linkage") or {}
        if link.get("mechanism_id") != e.get("mechanism_id"):
            fields_ok = False
        if link.get("economic_rationale") != e.get("economic_rationale"):
            fields_ok = False
        if not fields_ok:
            break
    findings.append(
        _finding(
            "ADV_REQUIRED_CONTRACT_FIELDS",
            severity="CRITICAL",
            status="PASS" if fields_ok else "REMAINING",
            detail="input/feature/signal/entry/exit/failure/cost/risk/replay/negative/rationale",
        )
    )

    bad_labels = [e["label"] for e in report["executors"] if e.get("label") not in ALLOWED_LABELS]
    findings.append(
        _finding(
            "ADV_LABEL_ALLOWLIST",
            severity="CRITICAL",
            status="PASS" if not bad_labels else "REMAINING",
            detail="illegal_labels=" + ",".join(bad_labels) if bad_labels else "all labels allowed",
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
            for e in report["executors"]
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
        and report.get("pr27_merge_attempted") is False
        and report.get("auto_integrate_attempted") is False
        and set(HARD_BANS).issubset(set(report.get("hard_bans") or []))
    )
    findings.append(
        _finding(
            "ADV_HARD_BAN_COMPLIANCE",
            severity="CRITICAL",
            status="PASS" if bans_ok else "REMAINING",
            detail="oos/wf/demo/shadow/exchange/mainnet/pr27/auto-integrate bans held",
        )
    )

    replay_ok = bool(report.get("replay_stable")) and bool(report.get("campaign_digest"))
    findings.append(
        _finding(
            "ADV_DETERMINISTIC_REPLAY",
            severity="CRITICAL",
            status="PASS" if replay_ok else "REMAINING",
            detail=f"campaign_digest={(report.get('campaign_digest') or '')[:16]}",
        )
    )

    pit_ok = all(
        (e.get("signal_contract") or {}).get("lookahead_forbidden") is True
        and (e.get("signal_contract") or {}).get("future_bar_reference_allowed") is False
        for e in report["executors"]
    )
    findings.append(
        _finding(
            "ADV_PIT_SIGNAL_CONTRACT",
            severity="HIGH",
            status="PASS" if pit_ok else "REMAINING",
            detail="lookahead forbidden; future-bar refs disallowed",
        )
    )

    cost_ok = all(
        (e.get("cost_dependency") or {}).get("cost_authority") == report.get("cost_authority")
        for e in report["executors"]
    )
    findings.append(
        _finding(
            "ADV_COST_DEPENDENCY",
            severity="HIGH",
            status="PASS" if cost_ok else "REMAINING",
            detail="all executors link to canonical cost authority",
        )
    )

    neg_ok = all(
        bool(e.get("negative_test")) and bool(e.get("negative_test_covered"))
        for e in report["executors"]
    )
    findings.append(
        _finding(
            "ADV_NEGATIVE_TEST_COVERAGE",
            severity="HIGH",
            status="PASS" if neg_ok else "REMAINING",
            detail="each executor carries negative_test contract + coverage flag",
        )
    )

    vocab_ok = True
    for e in report["executors"]:
        label = str(e.get("label") or "").upper()
        for frag in BANNED_CLAIM_FRAGMENTS:
            if frag in label and frag == "QUALIFIED" and "NOT_QUALIFIED" in label:
                continue
            if frag in label:
                vocab_ok = False
        if label.endswith("QUALIFIED") and "NOT_QUALIFIED" not in label:
            vocab_ok = False
    findings.append(
        _finding(
            "ADV_BANNED_VOCAB",
            severity="CRITICAL",
            status="PASS" if vocab_ok else "REMAINING",
            detail="banned profitability/qualification vocabulary absent from labels",
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
        "schema": "v15_b_mechanism_execution_compiler_adversarial_v1",
        "pass": pass_name,
        "finding_count": len(findings),
        "remaining_count": len(remaining),
        "critical_remaining": len(critical_remaining),
        "high_remaining": len(high_remaining),
        "pass_ok": len(remaining) == 0,
        "hard_bans_checked": sorted(HARD_BANS),
        "findings": findings,
        "qualification_ready_count": qrc,
        "mechanism_executor_count": count,
        "campaign_digest": report.get("campaign_digest"),
    }
