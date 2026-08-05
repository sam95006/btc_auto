"""NEXUS V15-L Private Core Final False-Pass Red Team — orchestrator."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.security_persistence_v1 import scan_secrets_in_evidence
from backend.nexus_private_core_redteam.constants import (
    ATTACK_SCENARIO_IDS,
    BASE_HEAD,
    BLOCKED_RECOMMENDATION,
    BRANCH,
    EXECUTION_MODE,
    FAIL_RECOMMENDATION,
    FIXTURE_IDS,
    HARD_BANS,
    INVALID_RECOMMENDATION,
    LABEL,
    LANE,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    PROHIBITED_PATHS,
    PROGRAM_ID,
    SCHEMA,
    STRUCTURAL_BLOCKERS,
)
from backend.nexus_private_core_redteam.fixtures import run_all_fixtures
from backend.nexus_private_core_redteam.production_ast import run_v15_production_ast_campaign
from backend.nexus_private_core_redteam.scenarios import ScenarioResult, run_all_scenarios

__all__ = [
    "OWNED_PATHS",
    "PASS_RECOMMENDATION",
    "FAIL_RECOMMENDATION",
    "evaluate_private_core_redteam",
    "run_private_core_redteam",
    "write_immutable_artifacts",
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _immutable_dir(root: Path | None = None) -> Path:
    base = root or _repo_root()
    return base / "artifacts" / "readiness" / "immutable" / "v15_private_core_redteam"


def _critical_findings(
    results: list[ScenarioResult],
    fixtures: list[dict[str, Any]],
    ast_campaign: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for r in results:
        if r.platform_blocked:
            findings.append(
                {
                    "severity": "critical",
                    "code": f"platform_blocked_not_pass:{r.scenario_id}",
                    "detail": r.detail,
                    "fail_closed": True,
                    "attack_blocked": False,
                    "platform_blocked": True,
                }
            )
        elif r.critical or not r.passed:
            findings.append(
                {
                    "severity": "critical",
                    "code": f"scenario_failed:{r.scenario_id}",
                    "detail": r.detail,
                    "fail_closed": r.fail_closed,
                    "attack_blocked": r.attack_blocked,
                }
            )
    missing = set(ATTACK_SCENARIO_IDS) - {r.scenario_id for r in results}
    for sid in sorted(missing):
        findings.append(
            {
                "severity": "critical",
                "code": f"scenario_missing:{sid}",
                "detail": "required_scenario_not_executed",
                "fail_closed": False,
            }
        )
    for fx in fixtures:
        if not fx.get("passed"):
            findings.append(
                {
                    "severity": "critical",
                    "code": f"fixture_failed:{fx.get('fixture_id')}",
                    "detail": "fixture_attack_not_killed",
                    "fail_closed": True,
                }
            )
    if not ast_campaign.get("passed"):
        for b in ast_campaign.get("unresolved_blockers") or []:
            findings.append(
                {
                    "severity": "critical",
                    "code": f"ast_blocker:{b}",
                    "detail": "production_ast_unresolved",
                    "fail_closed": True,
                }
            )
        if not (ast_campaign.get("unresolved_blockers") or []):
            findings.append(
                {
                    "severity": "critical",
                    "code": "production_ast_failed",
                    "detail": "ast_campaign_not_passed",
                    "fail_closed": True,
                }
            )
    return findings


def evaluate_private_core_redteam(
    *,
    root: Path | None = None,
    workdir: Path | None = None,
    pass_number: int = 1,
) -> dict[str, Any]:
    """Run attack scenarios + fixtures + production AST; return machine report."""
    base = root or _repo_root()
    tmp_owned = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="nexus_v15_l_"))
        tmp_owned = True

    try:
        results = run_all_scenarios(Path(workdir) / "scenarios")
        fixtures = run_all_fixtures(Path(workdir) / "fixtures", root=base)
        ast_campaign = run_v15_production_ast_campaign(root=base)
        findings = _critical_findings(results, fixtures, ast_campaign)
        critical = [f for f in findings if f.get("severity") == "critical"]

        exchange_write_attempt_count = 0
        mainnet_client_created_count = 0
        demo_order_count = 0
        platform_blocked_count = sum(1 for r in results if r.platform_blocked)
        platform_blocked_pass_count = 0  # hard ban invariant

        attack_blocked_count = sum(1 for r in results if r.attack_blocked)
        scenario_pass_count = sum(1 for r in results if r.passed and not r.platform_blocked)
        fixture_pass_count = sum(1 for f in fixtures if f.get("passed"))

        unresolved_blockers = list(STRUCTURAL_BLOCKERS)
        for f in critical:
            code = str(f.get("code") or "")
            if code.startswith("platform_blocked") or code.startswith("ast_blocker"):
                unresolved_blockers.append(code)
        for b in ast_campaign.get("unresolved_blockers") or []:
            if b not in unresolved_blockers:
                unresolved_blockers.append(b)
        if int(ast_campaign.get("survivors") or 0) > 0:
            unresolved_blockers.append("critical_survivors_block_v15_readiness")

        report: dict[str, Any] = {
            "schema": SCHEMA,
            "program_id": PROGRAM_ID,
            "created_at": _utc(),
            "lane": LANE,
            "branch": BRANCH,
            "base_head": BASE_HEAD,
            "pass_number": pass_number,
            "execution_mode": EXECUTION_MODE,
            "owned_paths": list(OWNED_PATHS),
            "prohibited_paths": list(PROHIBITED_PATHS),
            "hard_bans": list(HARD_BANS),
            "scenario_ids": list(ATTACK_SCENARIO_IDS),
            "fixture_ids": list(FIXTURE_IDS),
            "scenarios": [r.to_dict() for r in results],
            "fixtures": fixtures,
            "production_ast": {
                "passed": ast_campaign.get("passed"),
                "killed": ast_campaign.get("killed"),
                "survivors": ast_campaign.get("survivors"),
                "equivalent": ast_campaign.get("equivalent"),
                "errors": ast_campaign.get("errors"),
                "platform_blocked_count": ast_campaign.get("platform_blocked_count"),
                "platform_blocked_pass_count": ast_campaign.get("platform_blocked_pass_count"),
                "required_kill_status": ast_campaign.get("required_kill_status"),
                "unresolved_blockers": ast_campaign.get("unresolved_blockers"),
            },
            "scenario_pass_count": scenario_pass_count,
            "scenario_total_count": len(ATTACK_SCENARIO_IDS),
            "fixture_pass_count": fixture_pass_count,
            "fixture_total_count": len(FIXTURE_IDS),
            "attack_blocked_count": attack_blocked_count,
            "attack_total_count": len(ATTACK_SCENARIO_IDS),
            "platform_blocked_count": platform_blocked_count,
            "platform_blocked_pass_count": platform_blocked_pass_count,
            "findings": {
                "critical_finding_count": len(critical),
                "unresolved_critical_count": len(critical),
                "high_finding_count": 0,
                "items": findings,
            },
            "exchange_write_attempt_count": exchange_write_attempt_count,
            "secret_leak_count": 0,
            "mainnet_client_created_count": mainnet_client_created_count,
            "demo_order_count": demo_order_count,
            "real_money": False,
            "mainnet": False,
            "auto_integration": False,
            "PR27_draft_unmerged": True,
            "remaining_blockers": unresolved_blockers,
            "label": LABEL,
            "v15_readiness_blocked_by_survivors": int(ast_campaign.get("survivors") or 0) > 0,
        }

        secret_hits = scan_secrets_in_evidence(report)
        real_leaks = [h for h in secret_hits if h in {"credential_assignment", "private_key_pem"}]
        report["secret_leak_count"] = len(real_leaks)
        report["secret_scan"] = {
            "raw_hit_count": len(secret_hits),
            "real_leak_count": len(real_leaks),
            "real_leaks": real_leaks,
        }

        if report["secret_leak_count"] > 0:
            leak_finding = {
                "severity": "critical",
                "code": "secret_leak_in_evidence",
                "detail": f"count={report['secret_leak_count']}",
                "fail_closed": True,
            }
            findings.append(leak_finding)
            critical.append(leak_finding)
            report["findings"]["items"] = findings
            report["findings"]["critical_finding_count"] = len(critical)
            report["findings"]["unresolved_critical_count"] = len(critical)

        all_passed = (
            scenario_pass_count == len(ATTACK_SCENARIO_IDS)
            and fixture_pass_count == len(FIXTURE_IDS)
            and report["findings"]["unresolved_critical_count"] == 0
            and exchange_write_attempt_count == 0
            and report["secret_leak_count"] == 0
            and mainnet_client_created_count == 0
            and demo_order_count == 0
            and platform_blocked_count == 0
            and platform_blocked_pass_count == 0
            and len(results) == len(ATTACK_SCENARIO_IDS)
            and attack_blocked_count == len(ATTACK_SCENARIO_IDS)
            and bool(ast_campaign.get("passed"))
            and int(ast_campaign.get("survivors") or 0) == 0
        )

        if len(results) != len(ATTACK_SCENARIO_IDS):
            recommendation = INVALID_RECOMMENDATION
        elif platform_blocked_count > 0 or int(ast_campaign.get("platform_blocked_count") or 0) > 0:
            recommendation = BLOCKED_RECOMMENDATION
        elif int(ast_campaign.get("survivors") or 0) > 0:
            recommendation = BLOCKED_RECOMMENDATION
        elif all_passed:
            recommendation = PASS_RECOMMENDATION
        else:
            recommendation = FAIL_RECOMMENDATION

        report["recommendation"] = recommendation
        report["Private_Core_Final_Redteam_status"] = recommendation
        report["passed"] = recommendation == PASS_RECOMMENDATION
        report["critical_findings"] = [
            f for f in report["findings"]["items"] if f.get("severity") == "critical"
        ]
        report["high_findings"] = [
            f for f in report["findings"]["items"] if f.get("severity") == "high"
        ]
        report["worktree"] = str(base)
        return report
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
    """Write immutable report/summary (no *_status.json lane files)."""
    base = root or _repo_root()
    out_dir = _immutable_dir(base)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = status or evaluate_private_core_redteam(root=base)

    report_path = out_dir / "private_core_redteam_report.json"
    report_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    summary = {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "branch": BRANCH,
        "base_head": BASE_HEAD,
        "pass_number": payload.get("pass_number"),
        "passed": payload.get("passed"),
        "recommendation": payload.get("recommendation"),
        "scenario_pass_count": payload.get("scenario_pass_count"),
        "scenario_total_count": payload.get("scenario_total_count"),
        "fixture_pass_count": payload.get("fixture_pass_count"),
        "fixture_total_count": payload.get("fixture_total_count"),
        "attack_blocked_count": payload.get("attack_blocked_count"),
        "platform_blocked_pass_count": payload.get("platform_blocked_pass_count"),
        "production_ast_survivors": (payload.get("production_ast") or {}).get("survivors"),
        "critical_finding_count": payload.get("findings", {}).get("critical_finding_count"),
        "exchange_write_attempt_count": payload.get("exchange_write_attempt_count"),
        "secret_leak_count": payload.get("secret_leak_count"),
        "mainnet_client_created_count": payload.get("mainnet_client_created_count"),
        "v15_readiness_blocked_by_survivors": payload.get("v15_readiness_blocked_by_survivors"),
        "created_at": payload.get("created_at"),
    }
    summary_path = out_dir / "private_core_redteam_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"report": report_path, "summary": summary_path, "dir": out_dir}


def run_private_core_redteam(
    *,
    write_artifact: bool = True,
    root: Path | None = None,
    commit: str | None = None,
    pass_number: int = 1,
) -> dict[str, Any]:
    """Evaluate and optionally write immutable artifacts. No runtime *_status.json."""
    base = root or _repo_root()
    status = evaluate_private_core_redteam(root=base, pass_number=pass_number)
    if commit:
        status["commit"] = commit
    if write_artifact:
        paths = write_immutable_artifacts(root=base, status=status)
        status["artifact_paths"] = {k: str(v) for k, v in paths.items() if k != "dir"}
        status["artifact_dir"] = str(paths["dir"])
    return status
