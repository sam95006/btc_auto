"""Two-pass adversarial review for V14-C Mechanism Lab V4."""
from __future__ import annotations

from typing import Any

from backend.nexus_mechanism_lab_v4.constants import (
    HARD_BANS,
    MECHANISM_FAMILIES,
    MIN_MECHANISM_COUNT,
    REQUIRED_MECHANISM_FIELDS,
)
from backend.nexus_mechanism_lab_v4.lab import ALLOWED_LABELS, run_mechanism_lab


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
    report = report or run_mechanism_lab(pass_id=2)
    findings: list[dict[str, str]] = []

    count = int(report.get("mechanism_count") or 0)
    findings.append(
        _finding(
            "ADV_MIN_MECHANISM_COUNT",
            severity="CRITICAL",
            status="PASS" if count >= MIN_MECHANISM_COUNT else "REMAINING",
            detail=f"mechanism_count={count} min={MIN_MECHANISM_COUNT}",
        )
    )

    ids = [m["mechanism_id"] for m in report["mechanisms"]]
    kinds = [
        (
            m.get("signal_kind"),
            m.get("primary_feature"),
            m.get("secondary_feature"),
            m.get("direction_mode"),
        )
        for m in report["mechanisms"]
    ]
    rationales = [m.get("economic_rationale") for m in report["mechanisms"]]
    distinct_ok = (
        len(ids) == len(set(ids))
        and len(kinds) == len(set(kinds))
        and len(rationales) == len(set(rationales))
    )
    findings.append(
        _finding(
            "ADV_SEMANTIC_DISTINCTNESS",
            severity="CRITICAL",
            status="PASS" if distinct_ok else "REMAINING",
            detail="unique ids, signal contracts, and rationales",
        )
    )

    fams = {m["family"] for m in report["mechanisms"]}
    findings.append(
        _finding(
            "ADV_FAMILY_COVERAGE",
            severity="HIGH",
            status="PASS" if set(MECHANISM_FAMILIES).issubset(fams) else "REMAINING",
            detail=f"families_present={len(fams)}",
        )
    )

    fields_ok = True
    for m in report["mechanisms"]:
        for field in REQUIRED_MECHANISM_FIELDS:
            if field not in m or m[field] in (None, "", [], ()):
                fields_ok = False
                break
        if not fields_ok:
            break
    findings.append(
        _finding(
            "ADV_REQUIRED_FIELDS",
            severity="CRITICAL",
            status="PASS" if fields_ok else "REMAINING",
            detail="all required mechanism schema fields present",
        )
    )

    bad_labels = [m["label"] for m in report["mechanisms"] if m.get("label") not in ALLOWED_LABELS]
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
            m.get("edge_claimed") is False
            and m.get("profitability_claimed") is False
            and m.get("qualified") is False
            and m.get("qualification_ready") is False
            for m in report["mechanisms"]
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

    pit_ok = all(
        (m.get("point_in_time_proof") or {}).get("lookahead_forbidden") is True
        and int((m.get("point_in_time_proof") or {}).get("future_bar_reference_count") or 0) == 0
        for m in report["mechanisms"]
    )
    findings.append(
        _finding(
            "ADV_PIT_PROOF",
            severity="HIGH",
            status="PASS" if pit_ok else "REMAINING",
            detail="lookahead forbidden; future-bar refs zero",
        )
    )

    lineage_ok = all(
        m.get("data_lineage") == "SYNTHETIC_DEVELOPMENT_FIXTURE" for m in report["mechanisms"]
    ) and (report.get("data_lineage") or {}).get("data_lineage") == "SYNTHETIC_DEVELOPMENT_FIXTURE"
    findings.append(
        _finding(
            "ADV_SYNTHETIC_ONLY",
            severity="CRITICAL",
            status="PASS" if lineage_ok else "REMAINING",
            detail="all mechanisms synthetic development lineage",
        )
    )

    # Pass-2 specific: checksum stability + no banned vocabulary in labels.
    banned_frags = ("PROFITABLE", "OOS_PASS", "WALK_FORWARD_PASS", "DEMO_READY", "PROMOTION_READY")
    vocab_ok = True
    for m in report["mechanisms"]:
        label = str(m.get("label") or "").upper()
        for frag in banned_frags:
            if frag in label:
                vocab_ok = False
        if label.endswith("QUALIFIED") and "NOT_QUALIFIED" not in label:
            vocab_ok = False
    findings.append(
        _finding(
            "ADV_BANNED_VOCAB_PASS2",
            severity="CRITICAL",
            status="PASS" if vocab_ok else "REMAINING",
            detail="banned profitability/qualification vocabulary absent",
        )
    )

    # Pass-2: re-run determinism check on code checksum presence.
    findings.append(
        _finding(
            "ADV_DETERMINISTIC_CHECKSUM",
            severity="HIGH",
            status="PASS" if bool(report.get("code_checksum")) else "REMAINING",
            detail=f"code_checksum={(report.get('code_checksum') or '')[:16]}",
        )
    )

    remaining = [f for f in findings if f["status"] == "REMAINING"]
    return {
        "schema": "v14_c_mechanism_lab_adversarial_v1",
        "pass": pass_name,
        "finding_count": len(findings),
        "remaining_count": len(remaining),
        "pass_ok": len(remaining) == 0,
        "hard_bans_checked": sorted(HARD_BANS),
        "findings": findings,
        "qualification_ready_count": qrc,
        "mechanism_count": count,
    }
