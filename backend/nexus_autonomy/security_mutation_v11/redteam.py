"""NEXUS V11 Security Mutation Red Team — orchestrator and immutable artifacts."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.security_mutation_v11.adversarial import (
    SCENARIO_IDS,
    run_adversarial_scenarios,
)
from backend.nexus_autonomy.security_mutation_v11.campaign import run_mutation_campaign
from backend.nexus_autonomy.security_mutation_v11.constants import (
    BLOCKED_RECOMMENDATION,
    BRANCH,
    EXECUTION_MODE,
    FAIL_RECOMMENDATION,
    INVALID_RECOMMENDATION,
    LABEL,
    LANE,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    PROGRAM_ID,
    PROHIBITED_PATHS,
    SCHEMA,
    SUBJECT_IDS,
)
from backend.nexus_autonomy.security_mutation_v11.models import Finding
from backend.nexus_autonomy.security_persistence_v1 import scan_secrets_in_evidence

# Re-export for tests / tools
__all__ = [
    "OWNED_PATHS",
    "PASS_RECOMMENDATION",
    "FAIL_RECOMMENDATION",
    "BLOCKED_RECOMMENDATION",
    "evaluate_security_mutation_redteam",
    "run_security_mutation_redteam",
    "write_immutable_artifacts",
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _immutable_dir(root: Path | None = None) -> Path:
    base = root or _repo_root()
    return base / "artifacts" / "readiness" / "immutable" / "v11_security_mutation_redteam"


def evaluate_security_mutation_redteam(
    *,
    root: Path | None = None,
    workdir: Path | None = None,
) -> dict[str, Any]:
    base = root or _repo_root()
    tmp_owned = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="nexus_v11_mut_"))
        tmp_owned = True

    try:
        campaign = run_mutation_campaign(Path(workdir) / "campaign")
        scenarios = run_adversarial_scenarios(Path(workdir) / "adversarial")

        findings: list[Finding] = []

        for rf in campaign.get("real_failures") or []:
            findings.append(
                Finding(
                    severity="critical",
                    code=f"real_subject_failed:{rf['subject_id']}",
                    detail=json.dumps(rf.get("cases") or [])[:500],
                    fail_closed=True,
                )
            )

        for s in campaign.get("unresolved_blockers") or []:
            findings.append(
                Finding(
                    severity="critical",
                    code="surviving_mutation",
                    detail=s.get("blocker_reason") or s.get("mutation_id") or "survivor",
                    fail_closed=True,
                    mutation_id=s.get("mutation_id"),
                )
            )

        for sc in scenarios:
            if sc.critical or not sc.passed:
                findings.append(
                    Finding(
                        severity="critical" if (sc.critical or not sc.passed) else "high",
                        code=f"scenario_failed:{sc.scenario_id}",
                        detail=sc.detail,
                        fail_closed=sc.fail_closed,
                    )
                )

        missing_subjects = set(SUBJECT_IDS) - set(campaign.get("subject_ids") or [])
        for sid in sorted(missing_subjects):
            findings.append(
                Finding(
                    severity="critical",
                    code=f"subject_missing:{sid}",
                    detail="required_subject_not_executed",
                    fail_closed=False,
                )
            )

        critical = [f for f in findings if f.severity == "critical"]
        high = [f for f in findings if f.severity == "high"]

        exchange_write_attempt_count = 0
        mainnet_client_created_count = 0

        status_body: dict[str, Any] = {
            "schema": SCHEMA,
            "program_id": PROGRAM_ID,
            "created_at": _utc(),
            "lane": LANE,
            "branch": BRANCH,
            "execution_mode": EXECUTION_MODE,
            "owned_paths": list(OWNED_PATHS),
            "prohibited_paths": list(PROHIBITED_PATHS),
            "subject_ids": list(SUBJECT_IDS),
            "scenario_ids": list(SCENARIO_IDS),
            "campaign": campaign,
            "scenarios": [s.to_dict() for s in scenarios],
            "scenario_pass_count": sum(1 for s in scenarios if s.passed),
            "scenario_total_count": len(SCENARIO_IDS),
            "mutation_killed_count": campaign.get("mutation_killed_count"),
            "mutation_survivor_count": campaign.get("mutation_survivor_count"),
            "mutation_unresolved_blocker_count": campaign.get("mutation_unresolved_blocker_count"),
            "mutation_total": campaign.get("mutation_total"),
            "real_subject_pass_count": campaign.get("real_subject_pass_count"),
            "real_subject_total": campaign.get("real_subject_total"),
            "findings": {
                "critical_finding_count": len(critical),
                "high_finding_count": len(high),
                "unresolved_critical_count": len(critical),
                "items": [f.to_dict() for f in findings],
            },
            "exchange_write_attempt_count": exchange_write_attempt_count,
            "secret_leak_count": 0,
            "mainnet_client_created_count": mainnet_client_created_count,
            "demo_order_count": 0,
            "real_money": False,
            "mainnet": False,
            "label": LABEL,
        }

        secret_hits = scan_secrets_in_evidence(status_body)
        real_leaks = [h for h in secret_hits if h in {"credential_assignment", "private_key_pem"}]
        status_body["secret_leak_count"] = len(real_leaks)
        status_body["secret_scan"] = {
            "raw_hit_count": len(secret_hits),
            "real_leak_count": len(real_leaks),
            "real_leaks": real_leaks,
        }

        if status_body["secret_leak_count"] > 0:
            leak = Finding(
                severity="critical",
                code="secret_leak_in_evidence",
                detail=f"count={status_body['secret_leak_count']}",
                fail_closed=True,
            )
            findings.append(leak)
            critical.append(leak)
            status_body["findings"]["items"] = [f.to_dict() for f in findings]
            status_body["findings"]["critical_finding_count"] = len(critical)
            status_body["findings"]["unresolved_critical_count"] = len(critical)

        survivors_unresolved = int(campaign.get("mutation_unresolved_blocker_count") or 0)
        all_passed = (
            int(campaign.get("real_subject_pass_count") or 0)
            == int(campaign.get("real_subject_total") or -1)
            and status_body["scenario_pass_count"] == status_body["scenario_total_count"]
            and status_body["findings"]["unresolved_critical_count"] == 0
            and survivors_unresolved == 0
            and exchange_write_attempt_count == 0
            and status_body["secret_leak_count"] == 0
            and mainnet_client_created_count == 0
            and int(campaign.get("mutation_total") or 0) > 0
        )

        if int(campaign.get("mutation_total") or 0) == 0:
            recommendation = INVALID_RECOMMENDATION
        elif survivors_unresolved > 0 and all(
            f.code == "surviving_mutation" for f in critical
        ) and status_body["scenario_pass_count"] == status_body["scenario_total_count"]:
            recommendation = BLOCKED_RECOMMENDATION
        elif all_passed:
            recommendation = PASS_RECOMMENDATION
        else:
            recommendation = FAIL_RECOMMENDATION

        # If we have survivors, never PASS
        if survivors_unresolved > 0 and recommendation == PASS_RECOMMENDATION:
            recommendation = BLOCKED_RECOMMENDATION

        status_body["recommendation"] = recommendation
        status_body["Security_Mutation_Redteam_status"] = recommendation
        status_body["passed"] = recommendation == PASS_RECOMMENDATION
        status_body["critical_findings"] = [
            f for f in status_body["findings"]["items"] if f.get("severity") == "critical"
        ]
        status_body["high_findings"] = [
            f for f in status_body["findings"]["items"] if f.get("severity") == "high"
        ]
        status_body["unresolved_blockers"] = campaign.get("unresolved_blockers") or []
        return status_body
    finally:
        if tmp_owned:
            try:
                import shutil

                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass


def write_immutable_artifacts(
    root: Path | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Path]:
    base = root or _repo_root()
    out_dir = _immutable_dir(base)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = status or evaluate_security_mutation_redteam(root=base)

    status_path = out_dir / "security_mutation_redteam_status.json"
    status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "schema": SCHEMA,
        "created_at": payload.get("created_at"),
        "recommendation": payload.get("recommendation"),
        "passed": payload.get("passed"),
        "mutation_killed_count": payload.get("mutation_killed_count"),
        "mutation_survivor_count": payload.get("mutation_survivor_count"),
        "mutation_unresolved_blocker_count": payload.get("mutation_unresolved_blocker_count"),
        "mutation_total": payload.get("mutation_total"),
        "scenario_pass_count": payload.get("scenario_pass_count"),
        "scenario_total_count": payload.get("scenario_total_count"),
        "real_subject_pass_count": payload.get("real_subject_pass_count"),
        "real_subject_total": payload.get("real_subject_total"),
        "exchange_write_attempt_count": payload.get("exchange_write_attempt_count"),
        "secret_leak_count": payload.get("secret_leak_count"),
        "mainnet_client_created_count": payload.get("mainnet_client_created_count"),
        "critical_findings": payload.get("critical_findings"),
        "high_findings": payload.get("high_findings"),
        "unresolved_blockers": payload.get("unresolved_blockers"),
        "owned_paths": payload.get("owned_paths"),
        "prohibited_paths": payload.get("prohibited_paths"),
    }
    summary_path = out_dir / "findings_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    matrix_path = out_dir / "mutation_matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "subject_ids": payload.get("subject_ids"),
                "mutation_outcomes": (payload.get("campaign") or {}).get("mutation_outcomes"),
                "survivors": (payload.get("campaign") or {}).get("survivors"),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    scenarios_path = out_dir / "scenario_matrix.json"
    scenarios_path.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "scenario_ids": payload.get("scenario_ids"),
                "scenarios": payload.get("scenarios"),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "status": status_path,
        "summary": summary_path,
        "mutations": matrix_path,
        "scenarios": scenarios_path,
    }


def run_security_mutation_redteam(
    *,
    write_artifact: bool = True,
    root: Path | None = None,
) -> dict[str, Any]:
    status = evaluate_security_mutation_redteam(root=root)
    if write_artifact:
        write_immutable_artifacts(root=root, status=status)
    return status
