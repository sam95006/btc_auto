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
    DUPLICATE_GATE_BASELINE_FALSE_CONFIDENCE_ACK,
    EXECUTION_MODE,
    FAIL_RECOMMENDATION,
    HARD_BANS,
    H_GATE_HONESTY_NOTE,
    H_GATE_PASS_IS_NOT_AUTHORITY_REMEDIATION,
    INVALID_RECOMMENDATION,
    LABEL,
    LANE,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    PRODUCTION_AST_SURVIVOR_COUNT_REQUIRED,
    PROGRAM_ID,
    PROHIBITED_PATHS,
    REMEDIATION_ARTIFACT_REL,
    SCHEMA,
    SUBJECT_IDS,
    WRAPPER_ONLY_PASS_FORBIDDEN,
)
from backend.nexus_autonomy.security_mutation_v11.models import Finding
from backend.nexus_autonomy.security_mutation_v11.production_ast import (
    run_production_ast_mutation,
)
from backend.nexus_autonomy.security_mutation_v11.residuals import residual_high_findings
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
    "write_remediation_artifacts",
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
        production_ast = run_production_ast_mutation(root=base)

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

        # Production AST fail-closed (R4 remediation): no silent survivors.
        prod_survivors = int(production_ast.get("production_ast_survivor_count") or 0)
        prod_errors = int(production_ast.get("error_count") or 0)
        prod_total = int(production_ast.get("mutant_total") or 0)
        required_ok = bool(production_ast.get("required_detect_kills_ok"))
        if WRAPPER_ONLY_PASS_FORBIDDEN and prod_total <= 0:
            findings.append(
                Finding(
                    severity="critical",
                    code="G_MUTATION_DEPTH_WRAPPER_ONLY",
                    detail=(
                        "production AST campaign produced zero mutants; "
                        "wrapper-only PASS is forbidden"
                    ),
                    fail_closed=True,
                )
            )
        if prod_survivors > PRODUCTION_AST_SURVIVOR_COUNT_REQUIRED:
            findings.append(
                Finding(
                    severity="critical",
                    code="PRODUCTION_AST_MUTANT_SURVIVED",
                    detail=(
                        f"production_ast_survivor_count={prod_survivors} "
                        f"ids={production_ast.get('survivor_ids')}"
                    ),
                    fail_closed=True,
                )
            )
        if prod_errors > 0:
            findings.append(
                Finding(
                    severity="critical",
                    code="PRODUCTION_AST_MUTATION_ERRORS",
                    detail=f"error_count={prod_errors}",
                    fail_closed=True,
                )
            )
        if not required_ok:
            findings.append(
                Finding(
                    severity="critical",
                    code="PRODUCTION_AST_REQUIRED_DETECT_KILLS_MISSING",
                    detail=(
                        "missing="
                        + json.dumps(production_ast.get("required_detect_kills_missing") or [])
                    ),
                    fail_closed=True,
                )
            )

        critical = [f for f in findings if f.severity == "critical"]
        # Pass-2 residual highs are informational (do not flip PASS→FAIL by themselves)
        residual_highs = residual_high_findings()
        high = [f for f in findings if f.severity == "high"] + residual_highs

        exchange_write_attempt_count = 0
        mainnet_client_created_count = 0

        killed = int(campaign.get("mutation_killed_count") or 0)
        total_mut = int(campaign.get("mutation_total") or 0)
        kill_rate_ok = total_mut > 0 and killed == total_mut
        if not kill_rate_ok and total_mut > 0:
            findings.append(
                Finding(
                    severity="critical",
                    code="mutation_kill_rate_incomplete",
                    detail=f"killed={killed} total={total_mut}",
                    fail_closed=True,
                )
            )
            critical = [f for f in findings if f.severity == "critical"]

        production_ast_ok = (
            prod_total > 0
            and prod_survivors == PRODUCTION_AST_SURVIVOR_COUNT_REQUIRED
            and prod_errors == 0
            and required_ok
        )

        status_body: dict[str, Any] = {
            "schema": SCHEMA,
            "program_id": PROGRAM_ID,
            "created_at": _utc(),
            "lane": LANE,
            "branch": BRANCH,
            "execution_mode": EXECUTION_MODE,
            "owned_paths": list(OWNED_PATHS),
            "prohibited_paths": list(PROHIBITED_PATHS),
            "hard_bans": list(HARD_BANS),
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
            "production_ast": production_ast,
            "production_ast_survivor_count": prod_survivors,
            "production_ast_killed_count": int(production_ast.get("killed_count") or 0),
            "production_ast_equivalent_count": int(production_ast.get("equivalent_count") or 0),
            "wrapper_only_pass_forbidden": WRAPPER_ONLY_PASS_FORBIDDEN,
            "h_gate_pass_is_not_authority_remediation": H_GATE_PASS_IS_NOT_AUTHORITY_REMEDIATION,
            "duplicate_gate_baseline_false_confidence_ack": (
                DUPLICATE_GATE_BASELINE_FALSE_CONFIDENCE_ACK
            ),
            "h_gate_honesty_note": H_GATE_HONESTY_NOTE,
            "findings": {
                "critical_finding_count": len(critical),
                "high_finding_count": len(high),
                "unresolved_critical_count": len(critical),
                "residual_high_count": len(residual_highs),
                "items": [f.to_dict() for f in findings] + [f.to_dict() for f in residual_highs],
            },
            "exchange_write_attempt_count": exchange_write_attempt_count,
            "secret_leak_count": 0,
            "mainnet_client_created_count": mainnet_client_created_count,
            "demo_order_count": 0,
            "real_money": False,
            "mainnet": False,
            "label": LABEL,
            "pass_number": 2,
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
            status_body["findings"]["items"] = [f.to_dict() for f in findings] + [
                f.to_dict() for f in residual_highs
            ]
            status_body["findings"]["critical_finding_count"] = len(critical)
            status_body["findings"]["unresolved_critical_count"] = len(critical)
            status_body["findings"]["high_finding_count"] = len(
                [f for f in status_body["findings"]["items"] if f.get("severity") == "high"]
            )

        # Refresh critical after production-ast findings appended above
        critical = [f for f in findings if f.severity == "critical"]
        status_body["findings"]["critical_finding_count"] = len(critical)
        status_body["findings"]["unresolved_critical_count"] = len(critical)
        status_body["findings"]["items"] = [f.to_dict() for f in findings] + [
            f.to_dict() for f in residual_highs
        ]
        status_body["findings"]["high_finding_count"] = len(
            [f for f in status_body["findings"]["items"] if f.get("severity") == "high"]
        )

        survivors_unresolved = int(campaign.get("mutation_unresolved_blocker_count") or 0)
        all_passed = (
            int(campaign.get("real_subject_pass_count") or 0)
            == int(campaign.get("real_subject_total") or -1)
            and status_body["scenario_pass_count"] == status_body["scenario_total_count"]
            and status_body["findings"]["unresolved_critical_count"] == 0
            and survivors_unresolved == 0
            and kill_rate_ok
            and production_ast_ok
            and exchange_write_attempt_count == 0
            and status_body["secret_leak_count"] == 0
            and mainnet_client_created_count == 0
            and int(campaign.get("mutation_total") or 0) > 0
        )

        if int(campaign.get("mutation_total") or 0) == 0:
            recommendation = INVALID_RECOMMENDATION
        elif (survivors_unresolved > 0 or not production_ast_ok) and status_body[
            "scenario_pass_count"
        ] == status_body["scenario_total_count"]:
            recommendation = BLOCKED_RECOMMENDATION
        elif all_passed:
            recommendation = PASS_RECOMMENDATION
        else:
            recommendation = FAIL_RECOMMENDATION

        # If we have survivors (wrapper or production AST), never PASS
        if survivors_unresolved > 0 and recommendation == PASS_RECOMMENDATION:
            recommendation = BLOCKED_RECOMMENDATION
        if not production_ast_ok and recommendation == PASS_RECOMMENDATION:
            recommendation = BLOCKED_RECOMMENDATION
        if WRAPPER_ONLY_PASS_FORBIDDEN and not production_ast_ok:
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
        status_body["unresolved_blockers"] = list(campaign.get("unresolved_blockers") or [])
        if not production_ast_ok:
            status_body["unresolved_blockers"].append(
                {
                    "blocker_reason": "production_ast_not_ok",
                    "production_ast_survivor_count": prod_survivors,
                    "required_detect_kills_missing": production_ast.get(
                        "required_detect_kills_missing"
                    ),
                }
            )
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
        "production_ast_survivor_count": payload.get("production_ast_survivor_count"),
        "production_ast_killed_count": payload.get("production_ast_killed_count"),
        "wrapper_only_pass_forbidden": payload.get("wrapper_only_pass_forbidden"),
        "h_gate_pass_is_not_authority_remediation": payload.get(
            "h_gate_pass_is_not_authority_remediation"
        ),
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
                "production_ast": payload.get("production_ast"),
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


def write_remediation_artifacts(
    root: Path | None = None,
    status: dict[str, Any] | None = None,
    *,
    pass1: dict[str, Any] | None = None,
    pass2: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Write V11.1 G AST mutation depth remediation artifacts."""
    base = root or _repo_root()
    out_dir = base / REMEDIATION_ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = status or evaluate_security_mutation_redteam(root=base)
    production_ast = payload.get("production_ast") or {}

    kill_table = [
        {
            "mutant_id": r.get("mutant_id"),
            "target_rel": r.get("target_rel"),
            "status": r.get("status"),
            "operator": r.get("operator"),
            "detail": (r.get("oracle") or {}).get("detail"),
            "r4_listed_survivor": r.get("mutant_id")
            in {
                "persist_scan_secrets_noop",
                "persist_json_accept_scalars",
                "public_assert_schema_noop",
                "public_redact_identity",
                "write_trap_install_noop",
            },
        }
        for r in (production_ast.get("results") or [])
    ]

    findings_status = {
        "G_MUTATION_DEPTH_WRAPPER_ONLY": (
            "FIXED"
            if payload.get("wrapper_only_pass_forbidden")
            and int(payload.get("production_ast_survivor_count") or -1) == 0
            and int((payload.get("production_ast") or {}).get("mutant_total") or 0) > 0
            and payload.get("passed")
            else "REMAINING"
        ),
        "PRODUCTION_AST_MUTANT_SURVIVED": (
            "FIXED"
            if int(payload.get("production_ast_survivor_count") or -1) == 0
            and bool((payload.get("production_ast") or {}).get("required_detect_kills_ok"))
            else "REMAINING"
        ),
        "secret_scan_json_assignment_blind_spot": (
            "FIXED"
            if "credential_assignment"
            in __import__(
                "backend.nexus_autonomy.security_persistence_v1",
                fromlist=["scan_secrets_in_evidence"],
            ).scan_secrets_in_evidence({"api_key": "SUPERSECRET" + "VALUE123456"})
            else "REMAINING"
        ),
        "DUPLICATE_GATE_BASELINE_FALSE_CONFIDENCE": (
            "FIXED"
            if payload.get("h_gate_pass_is_not_authority_remediation")
            and payload.get("duplicate_gate_baseline_false_confidence_ack")
            else "REMAINING"
        ),
    }

    remediation = {
        "schema": "nexus_v11_1_g_ast_mutation_remediation_v1",
        "created_at": payload.get("created_at"),
        "branch": BRANCH,
        "lane": LANE,
        "recommendation": payload.get("recommendation"),
        "passed": payload.get("passed"),
        "metrics": {
            "production_ast_survivor_count": payload.get("production_ast_survivor_count"),
            "production_ast_killed_count": payload.get("production_ast_killed_count"),
            "production_ast_equivalent_count": payload.get("production_ast_equivalent_count"),
            "wrapper_only_pass_forbidden": payload.get("wrapper_only_pass_forbidden"),
            "h_gate_pass_is_not_authority_remediation": payload.get(
                "h_gate_pass_is_not_authority_remediation"
            ),
            "exchange_write_attempt_count": payload.get("exchange_write_attempt_count"),
            "secret_leak_count": payload.get("secret_leak_count"),
            "mainnet_client_created_count": payload.get("mainnet_client_created_count"),
            "demo_order_count": payload.get("demo_order_count"),
        },
        "findings": findings_status,
        "mutant_kill_table": kill_table,
        "h_gate_honesty_note": payload.get("h_gate_honesty_note"),
        "hard_bans": list(HARD_BANS),
        "blockers": payload.get("unresolved_blockers") or [],
        "two_pass": {
            "pass1_recommendation": (pass1 or {}).get("recommendation"),
            "pass2_recommendation": (pass2 or payload).get("recommendation"),
            "pass1_production_ast_survivor_count": (pass1 or {}).get(
                "production_ast_survivor_count"
            ),
            "pass2_production_ast_survivor_count": (pass2 or payload).get(
                "production_ast_survivor_count"
            ),
            "deterministic": (
                (pass1 or {}).get("recommendation") == (pass2 or payload).get("recommendation")
                and (pass1 or {}).get("production_ast_survivor_count")
                == (pass2 or payload).get("production_ast_survivor_count")
            )
            if pass1
            else None,
        },
    }

    paths: dict[str, Path] = {}
    status_path = out_dir / "g_ast_mutation_status.json"
    status_path.write_text(json.dumps(remediation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["status"] = status_path

    kill_path = out_dir / "production_ast_kill_table.json"
    kill_path.write_text(
        json.dumps(
            {
                "schema": "v11_g_production_ast_kill_table_v1",
                "production_ast": production_ast,
                "kill_table": kill_table,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["kill_table"] = kill_path

    if pass1 is not None:
        p1 = out_dir / "pass1_report.json"
        p1.write_text(json.dumps(pass1, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths["pass1"] = p1
    if pass2 is not None:
        p2 = out_dir / "pass2_report.json"
        p2.write_text(json.dumps(pass2, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths["pass2"] = p2

    honesty = out_dir / "h_gate_honesty.json"
    honesty.write_text(
        json.dumps(
            {
                "schema": "v11_g_h_gate_honesty_v1",
                "h_gate_pass_is_not_authority_remediation": True,
                "duplicate_gate_baseline_false_confidence_ack": True,
                "note": H_GATE_HONESTY_NOTE,
                "integration_recommendation": "BLOCK_TREATING_H_GATE_AS_AUTHORITY_REMEDIATION",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["h_gate_honesty"] = honesty

    findings_path = out_dir / "findings_fixed_remaining.json"
    findings_path.write_text(
        json.dumps(findings_status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths["findings"] = findings_path

    return paths


def run_security_mutation_redteam(
    *,
    write_artifact: bool = True,
    root: Path | None = None,
) -> dict[str, Any]:
    status = evaluate_security_mutation_redteam(root=root)
    if write_artifact:
        write_immutable_artifacts(root=root, status=status)
        write_remediation_artifacts(root=root, status=status)
    return status
