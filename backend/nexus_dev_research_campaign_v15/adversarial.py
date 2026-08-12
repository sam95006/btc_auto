"""Adversarial Pass-2 review for V15-C — false PASS / banned claims / OOS / status.json."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_dev_research_campaign_v15.constants import ALLOWED_LABELS, ARTIFACT_DIRNAME
from backend.nexus_dev_research_campaign_v15.hard_bans import (
    HardBanViolation,
    assert_no_status_json,
    refuse_auto_integrate,
    refuse_exchange_write,
    refuse_formal_walk_forward,
    refuse_oos_consume,
    scan_owned_paths_for_banned_claims,
)
from backend.nexus_dev_research_campaign_v15.labeling import assert_label_allowed


def run_adversarial_review(
    report: dict[str, Any],
    *,
    root: Path,
    pass_name: str = "pass_2",
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    hist = report.get("label_histogram") or {}
    for lab_name in hist:
        if lab_name not in ALLOWED_LABELS:
            findings.append(
                {
                    "severity": "CRITICAL",
                    "code": "BANNED_LABEL_EMITTED",
                    "detail": lab_name,
                }
            )

    if int(report.get("qualification_ready_count", 1)) != 0:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "QUALIFICATION_READY_NONZERO",
                "detail": report.get("qualification_ready_count"),
            }
        )

    if report.get("qualified_claimed") or report.get("profitability_claimed"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "FORBIDDEN_CLAIM_FLAG",
                "detail": {
                    "qualified_claimed": report.get("qualified_claimed"),
                    "profitability_claimed": report.get("profitability_claimed"),
                },
            }
        )

    if report.get("oos_consumed") or report.get("oos_executed") or report.get("formal_walk_forward_executed"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "OOS_OR_WF_EXECUTED",
                "detail": {
                    "oos_consumed": report.get("oos_consumed"),
                    "oos_executed": report.get("oos_executed"),
                    "formal_walk_forward_executed": report.get("formal_walk_forward_executed"),
                },
            }
        )

    if report.get("data_lineage") == "FIXTURE_NOT_REAL":
        # Fixtures allowed only when clearly labeled; must not be called real.
        if "REAL" in str(report.get("development_interval_id") or "") and "FIXTURE" not in str(
            report.get("development_interval_id") or ""
        ):
            findings.append(
                {
                    "severity": "CRITICAL",
                    "code": "FIXTURE_MISLABELED_AS_REAL",
                    "detail": report.get("development_interval_id"),
                }
            )
        if report.get("fixture_never_called_real") is not True:
            findings.append(
                {
                    "severity": "HIGH",
                    "code": "FIXTURE_REAL_FLAG_MISSING",
                    "detail": "fixture_never_called_real must be true",
                }
            )

    if report.get("data_lineage") not in {
        "REAL_HISTORICAL_DEVELOPMENT",
        "FIXTURE_NOT_REAL",
    }:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "UNKNOWN_DATA_LINEAGE",
                "detail": report.get("data_lineage"),
            }
        )

    for ev in report.get("evaluations") or []:
        try:
            assert_label_allowed(str(ev.get("label")))
        except ValueError as exc:
            findings.append(
                {
                    "severity": "CRITICAL",
                    "code": "EVAL_LABEL_ILLEGAL",
                    "detail": str(exc),
                }
            )
        if ev.get("qualified") or ev.get("qualification_ready"):
            findings.append(
                {
                    "severity": "CRITICAL",
                    "code": "EVAL_QUALIFIED_FLAG",
                    "detail": ev.get("mechanism_id"),
                }
            )

    for name, fn in (
        ("OOS", refuse_oos_consume),
        ("WF", refuse_formal_walk_forward),
        ("EXCHANGE", refuse_exchange_write),
        ("AUTO_INTEGRATE", refuse_auto_integrate),
    ):
        try:
            fn()
            findings.append(
                {
                    "severity": "CRITICAL",
                    "code": f"HARD_BAN_{name}_NOT_ENFORCED",
                    "detail": "refuse API did not raise",
                }
            )
        except HardBanViolation:
            pass

    banned = scan_owned_paths_for_banned_claims(root)
    if not banned.get("ok", False):
        findings.append(
            {
                "severity": "HIGH",
                "code": "BANNED_CLAIM_SCAN_HITS",
                "detail": {"count": banned.get("banned_claim_count"), "hits": banned.get("hits")},
            }
        )

    art = root / "artifacts" / "readiness" / "immutable" / ARTIFACT_DIRNAME
    status_scan = assert_no_status_json(art)
    if not status_scan.get("ok", False):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "STATUS_JSON_PRESENT",
                "detail": status_scan.get("offenders"),
            }
        )

    if int(report.get("mechanism_count") or 0) < 40:
        findings.append(
            {
                "severity": "HIGH",
                "code": "MECHANISM_COUNT_BELOW_CATALOG",
                "detail": report.get("mechanism_count"),
            }
        )

    critical = [f for f in findings if f.get("severity") == "CRITICAL"]
    high = [f for f in findings if f.get("severity") == "HIGH"]
    return {
        "pass": pass_name,
        "findings": findings,
        "critical_count": len(critical),
        "high_count": len(high),
        "adversarial_ok": len(critical) == 0 and len(high) == 0,
        "banned_claim_scan": banned,
        "status_json_scan": status_scan,
        "remaining_count": len(critical) + len(high),
    }
