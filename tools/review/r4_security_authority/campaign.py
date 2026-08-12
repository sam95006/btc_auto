"""Two-pass R4 Security + Authority review campaign."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.review.r4_security_authority.authority_review import run_authority_review
from tools.review.r4_security_authority.constants import (
    ARTIFACT_REL,
    BASE_SHA,
    BLOCKED_RECOMMENDATION,
    BRANCH,
    EXECUTION_MODE,
    FAIL_RECOMMENDATION,
    LABEL,
    LANE,
    ORIGIN_G_BRANCH,
    ORIGIN_G_HEAD,
    ORIGIN_H_BRANCH,
    ORIGIN_H_HEAD,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    PROGRAM_ID,
    SCHEMA,
)
from tools.review.r4_security_authority.lane_g_audit import audit_lane_g_mutation_depth
from tools.review.r4_security_authority.origin_loader import resolve_origin_roots
from tools.review.r4_security_authority.production_mutation import run_production_ast_mutation
from tools.review.r4_security_authority.security_static import run_security_static_suite


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _collect_findings(
    g_audit: dict[str, Any],
    auth: dict[str, Any],
    static: dict[str, Any],
    mutation: dict[str, Any],
    pass_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    critical: list[dict[str, Any]] = []
    high: list[dict[str, Any]] = []

    if g_audit.get("finding"):
        critical.append({**g_audit["finding"], "pass": pass_id})

    for f in auth.get("findings") or []:
        row = {**f, "pass": pass_id}
        if row.get("severity") == "critical":
            critical.append(row)
        elif row.get("severity") == "high":
            high.append(row)

    # Secret JSON assignment blind spot
    for chk in static.get("checks") or []:
        if chk.get("check") == "secret_detection" and chk.get(
            "credential_assignment_json_blind_spot"
        ):
            high.append(
                {
                    "severity": "high",
                    "code": "secret_scan_json_assignment_blind_spot",
                    "detail": (
                        "credential_assignment regex misses JSON \"api_key\": \"...\" form; "
                        "substring patterns may still hit. Confirmed by R4 static suite."
                    ),
                    "fail_closed": False,
                    "pass": pass_id,
                }
            )
        if chk.get("check") == "symlink_escape" and chk.get("platform_skip"):
            high.append(
                {
                    "severity": "high",
                    "code": "symlink_escape_platform_dependent",
                    "detail": chk.get("detail")
                    or "Symlink creation unavailable; jail not production-proven on this host.",
                    "fail_closed": False,
                    "pass": pass_id,
                }
            )
        if chk.get("check") == "unsafe_deserialization" and not chk.get("passed"):
            critical.append(
                {
                    "severity": "critical",
                    "code": "UNSAFE_DESERIALIZATION_GAP",
                    "detail": chk,
                    "pass": pass_id,
                }
            )
        if chk.get("check") == "path_traversal" and not chk.get("passed"):
            critical.append(
                {
                    "severity": "critical",
                    "code": "PATH_TRAVERSAL_GAP",
                    "detail": chk,
                    "pass": pass_id,
                }
            )
        if chk.get("check") == "demo_mainnet_boundary" and not chk.get("passed"):
            critical.append(
                {
                    "severity": "critical",
                    "code": "DEMO_MAINNET_BOUNDARY_GAP",
                    "detail": chk,
                    "pass": pass_id,
                }
            )

    # Production AST survivors are critical — production guards can be silently weakened
    for row in mutation.get("results") or []:
        if row.get("status") == "survived":
            critical.append(
                {
                    "severity": "critical",
                    "code": "PRODUCTION_AST_MUTANT_SURVIVED",
                    "detail": row,
                    "pass": pass_id,
                    "fail_closed": True,
                }
            )

    # Lane G claimed PASS without production AST — already critical via g_audit.
    # Elevate residual if G high findings not tracked
    return critical, high


def _dedupe(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for f in findings:
        key = f"{f.get('code')}::{json.dumps(f.get('detail'), sort_keys=True, default=str)[:180]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _pass_adversarial_review(
    critical: list[dict[str, Any]],
    high: list[dict[str, Any]],
    mutation: dict[str, Any],
    g_audit: dict[str, Any],
) -> dict[str, Any]:
    """Pass-2 meta review: look for false PASS / fixture-only proof."""
    false_pass_flags: list[dict[str, Any]] = []

    if g_audit.get("lane_g_passed") and g_audit.get("mutation_depth") == "wrapper_in_memory":
        false_pass_flags.append(
            {
                "code": "LANE_G_FALSE_CONFIDENCE_PASS",
                "detail": (
                    "Lane G recommendation is PASS while mutation depth is wrapper-only. "
                    "Treat as incomplete evidence for production security mutant detection."
                ),
            }
        )

    if mutation.get("survivor_count", 0) == 0 and mutation.get("killed_count", 0) == 0:
        false_pass_flags.append(
            {
                "code": "R4_MUTATION_EMPTY",
                "detail": "No production AST mutants executed — review would be fixture-only.",
            }
        )

    # If all mutants killed but G was wrapper-only, still keep G critical
    if not any(c.get("code") == "G_MUTATION_DEPTH_WRAPPER_ONLY" for c in critical):
        if g_audit.get("mutation_depth") == "wrapper_in_memory":
            false_pass_flags.append(
                {
                    "code": "MISSING_G_DEPTH_FINDING",
                    "detail": "Expected critical finding for wrapper-only G depth was absent.",
                }
            )

    # Production AST survivors without residual defenses = single-point-of-failure
    survivors = [
        r for r in (mutation.get("results") or []) if r.get("status") == "survived"
    ]
    if survivors and g_audit.get("lane_g_passed"):
        false_pass_flags.append(
            {
                "code": "G_PASS_DESPITE_PRODUCTION_AST_SURVIVORS",
                "detail": (
                    f"{len(survivors)} production AST mutants survived R4 oracles "
                    f"({[s.get('mutant_id') for s in survivors]}). Lane G PASS cannot "
                    "stand as production-module mutation evidence."
                ),
            }
        )

    multi_scope_domains = {
        (c.get("domain") or (c.get("detail") or {}).get("domain"))
        for c in critical
        if c.get("code") == "MULTI_SCOPE_AUTHORITY"
    }
    for required in ("lifecycle", "checkpoint"):
        if required not in multi_scope_domains:
            false_pass_flags.append(
                {
                    "code": "MISSING_MULTI_SCOPE_DOMAIN",
                    "detail": f"Expected MULTI_SCOPE_AUTHORITY finding for domain={required}",
                }
            )

    return {
        "false_pass_flag_count": len(false_pass_flags),
        "false_pass_flags": false_pass_flags,
        "critical_count": len(critical),
        "high_count": len(high),
        "production_ast_killed": mutation.get("killed_count"),
        "production_ast_survivors": mutation.get("survivor_count"),
        "production_ast_survivor_ids": [s.get("mutant_id") for s in survivors],
    }


def run_single_pass(
    *,
    pass_id: int,
    root: Path,
    origin_g: Path,
    origin_h: Path,
) -> dict[str, Any]:
    g_audit = audit_lane_g_mutation_depth(origin_g)
    auth = run_authority_review(root, origin_h=origin_h)
    static = run_security_static_suite(root)
    mutation = run_production_ast_mutation(root)
    critical, high = _collect_findings(g_audit, auth, static, mutation, pass_id)
    critical = _dedupe(critical)
    high = _dedupe(high)
    adv = _pass_adversarial_review(critical, high, mutation, g_audit)

    # Integration recommendation
    unresolved_critical = len(critical)
    if unresolved_critical > 0:
        recommendation = BLOCKED_RECOMMENDATION
        integration = "BLOCK_LANE_G_H_INTEGRATION_UNTIL_REMEDIATION"
    elif high:
        recommendation = FAIL_RECOMMENDATION
        integration = "INTEGRATE_WITH_HIGH_RESIDUAL_TRACKING"
    else:
        recommendation = PASS_RECOMMENDATION
        integration = "CLEAR_FOR_CONTROLLED_INTEGRATION"

    # H is audit-only even when gate passes
    if auth.get("lane_h", {}).get("ci_gate_passed") and auth.get("critical_finding_count", 0) > 0:
        integration = "BLOCK_TREATING_H_GATE_AS_AUTHORITY_REMEDIATION"
        if recommendation == PASS_RECOMMENDATION:
            recommendation = BLOCKED_RECOMMENDATION

    return {
        "pass": pass_id,
        "generated_at": _utc(),
        "lane_g_audit": g_audit,
        "authority_review": auth,
        "security_static": static,
        "production_ast_mutation": mutation,
        "critical_findings": critical,
        "high_findings": high,
        "adversarial_review": adv,
        "recommendation": recommendation,
        "integration_recommendation": integration,
        "counters": {
            "exchange_write_attempt_count": 0,
            "secret_leak_count": int(static.get("secret_leak_count") or 0),
            "mainnet_client_created_count": 0,
            "false_PASS_count": int(adv.get("false_pass_flag_count") or 0),
            "authority_conflict_count": int(auth.get("critical_finding_count") or 0),
            "circular_scc_count": int(auth.get("circular_scc_count") or 0),
            "production_ast_killed_count": int(mutation.get("killed_count") or 0),
            "production_ast_survivor_count": int(mutation.get("survivor_count") or 0),
            "critical_finding_count": len(critical),
            "high_finding_count": len(high),
        },
    }


def run_r4_campaign(
    root: Path | None = None,
    origin_g: str | Path | None = None,
    origin_h: str | Path | None = None,
    passes: int = 2,
) -> dict[str, Any]:
    root = (root or _repo_root()).resolve()
    origins = resolve_origin_roots(origin_g, origin_h)
    out_dir = root / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    pass_reports: list[dict[str, Any]] = []
    for p in range(1, max(1, passes) + 1):
        report = run_single_pass(
            pass_id=p,
            root=root,
            origin_g=origins["g"],
            origin_h=origins["h"],
        )
        pass_reports.append(report)
        _write_json(out_dir / f"pass{p}_report.json", report)

    final = pass_reports[-1]
    # Merge findings across passes (union by code)
    all_critical = _dedupe([f for pr in pass_reports for f in pr["critical_findings"]])
    all_high = _dedupe([f for pr in pass_reports for f in pr["high_findings"]])

    status = {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "branch": BRANCH,
        "base_sha": BASE_SHA,
        "generated_at": _utc(),
        "label": LABEL,
        "execution_mode": EXECUTION_MODE,
        "owned_paths": list(OWNED_PATHS),
        "origin": {
            "g_branch": ORIGIN_G_BRANCH,
            "g_head": ORIGIN_G_HEAD,
            "g_root": str(origins["g"]),
            "h_branch": ORIGIN_H_BRANCH,
            "h_head": ORIGIN_H_HEAD,
            "h_root": str(origins["h"]),
        },
        "passes_completed": len(pass_reports),
        "pass_reports_present": [f"pass{i}_report.json" for i in range(1, len(pass_reports) + 1)],
        "recommendation": final["recommendation"],
        "integration_recommendation": final["integration_recommendation"],
        "critical_findings": all_critical,
        "high_findings": all_high,
        "counters": final["counters"],
        "production_ast_mutation_summary": {
            "tool": "custom_ast_mutator",
            "killed_count": final["production_ast_mutation"].get("killed_count"),
            "survivor_count": final["production_ast_mutation"].get("survivor_count"),
            "error_count": final["production_ast_mutation"].get("error_count"),
            "mutant_total": final["production_ast_mutation"].get("mutant_total"),
            "targets": final["production_ast_mutation"].get("targets"),
        },
        "lane_g_mutation_depth": final["lane_g_audit"].get("mutation_depth"),
        "lane_h_ci_gate_passed": final["authority_review"].get("lane_h", {}).get("ci_gate_passed"),
        "circular_scc_count": final["authority_review"].get("circular_scc_count"),
        "false_PASS_count": final["counters"].get("false_PASS_count"),
    }

    findings_summary = {
        "schema": SCHEMA,
        "created_at": _utc(),
        "recommendation": status["recommendation"],
        "integration_recommendation": status["integration_recommendation"],
        "passed": status["recommendation"] == PASS_RECOMMENDATION,
        "critical_findings": all_critical,
        "high_findings": all_high,
        "critical_count": len(all_critical),
        "high_count": len(all_high),
        "false_PASS_count": status["false_PASS_count"],
        "circular_scc_count": status["circular_scc_count"],
        "production_ast_killed_count": status["counters"]["production_ast_killed_count"],
        "production_ast_survivor_count": status["counters"]["production_ast_survivor_count"],
        "lane_g_mutation_depth": status["lane_g_mutation_depth"],
        "exchange_write_attempt_count": 0,
        "secret_leak_count": status["counters"]["secret_leak_count"],
        "mainnet_client_created_count": 0,
        "owned_paths": list(OWNED_PATHS),
    }

    _write_json(out_dir / "r4_security_authority_status.json", status)
    _write_json(out_dir / "findings_summary.json", findings_summary)
    _write_json(
        out_dir / "mutation_report.json",
        final["production_ast_mutation"],
    )
    _write_json(out_dir / "authority_review.json", final["authority_review"])
    _write_json(out_dir / "security_static.json", final["security_static"])
    _write_json(out_dir / "lane_g_depth_audit.json", final["lane_g_audit"])

    return status
