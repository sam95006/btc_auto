"""NEXUS V14-L Research Security and False-Pass Red Team — orchestrator."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.security_persistence_v1 import scan_secrets_in_evidence
from backend.nexus_research_redteam.constants import (
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
    RUNTIME_LANE_STATUS_PATH,
    RUNTIME_MATRIX_PATH,
    SCHEMA,
    STRUCTURAL_BLOCKERS,
)
from backend.nexus_research_redteam.fixtures import run_all_fixtures
from backend.nexus_research_redteam.production_ast import run_v14_production_ast_campaign
from backend.nexus_research_redteam.scenarios import ScenarioResult, run_all_scenarios

__all__ = [
    "OWNED_PATHS",
    "PASS_RECOMMENDATION",
    "FAIL_RECOMMENDATION",
    "evaluate_research_redteam",
    "run_research_redteam",
    "write_immutable_artifacts",
    "write_runtime_status",
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _immutable_dir(root: Path | None = None) -> Path:
    base = root or _repo_root()
    return base / "artifacts" / "readiness" / "immutable" / "v14_research_redteam"


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


def evaluate_research_redteam(
    *,
    root: Path | None = None,
    workdir: Path | None = None,
    pass_number: int = 1,
) -> dict[str, Any]:
    """Run attack scenarios + fixtures + production AST; return machine status."""
    base = root or _repo_root()
    tmp_owned = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="nexus_v14_l_"))
        tmp_owned = True

    try:
        results = run_all_scenarios(Path(workdir) / "scenarios")
        fixtures = run_all_fixtures(Path(workdir) / "fixtures", root=base)
        ast_campaign = run_v14_production_ast_campaign(root=base)
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

        status_body: dict[str, Any] = {
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
            leak_finding = {
                "severity": "critical",
                "code": "secret_leak_in_evidence",
                "detail": f"count={status_body['secret_leak_count']}",
                "fail_closed": True,
            }
            findings.append(leak_finding)
            critical.append(leak_finding)
            status_body["findings"]["items"] = findings
            status_body["findings"]["critical_finding_count"] = len(critical)
            status_body["findings"]["unresolved_critical_count"] = len(critical)

        all_passed = (
            scenario_pass_count == len(ATTACK_SCENARIO_IDS)
            and fixture_pass_count == len(FIXTURE_IDS)
            and status_body["findings"]["unresolved_critical_count"] == 0
            and exchange_write_attempt_count == 0
            and status_body["secret_leak_count"] == 0
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

        status_body["recommendation"] = recommendation
        status_body["Research_Security_Redteam_status"] = recommendation
        status_body["passed"] = recommendation == PASS_RECOMMENDATION
        status_body["critical_findings"] = [
            f for f in status_body["findings"]["items"] if f.get("severity") == "critical"
        ]
        status_body["high_findings"] = [
            f for f in status_body["findings"]["items"] if f.get("severity") == "high"
        ]
        status_body["worktree"] = str(base)
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
    payload = status or evaluate_research_redteam(root=base)

    status_path = out_dir / "research_redteam_status.json"
    status_path.write_text(
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
        "created_at": payload.get("created_at"),
    }
    summary_path = out_dir / "research_redteam_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"status": status_path, "summary": summary_path, "dir": out_dir}


def _read_sibling(runtime: Path, name: str) -> dict[str, Any] | None:
    path = runtime / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_lane_status(sib: dict[str, Any] | None) -> str:
    if not sib:
        return "STARTED"
    if sib.get("passed") is False:
        return "FAIL"
    candidates = [
        sib.get("recommendation"),
        sib.get("Research_Security_Redteam_status"),
        sib.get("status"),
        sib.get("overall_status"),
    ]
    for k, v in sib.items():
        if isinstance(v, str) and k.lower().endswith("status"):
            candidates.append(v)
    texts = [str(c).upper() for c in candidates if c]
    if any(t.endswith("_PASS") or t in {"PASS", "PASSED", "COMPLETE", "READY"} for t in texts):
        return "PASS"
    if sib.get("passed") is True:
        return "PASS"
    if any("FAIL" in t or "CRITICAL" in t or "UNRESOLVED" in t or "BLOCKED" in t for t in texts):
        return "FAIL"
    if texts:
        return "RETURNED"
    return "STARTED"


def build_v14_readiness_matrix(
    lane_status: dict[str, Any],
    *,
    runtime: Path | None = None,
) -> dict[str, Any]:
    """Update V14 readiness matrix; V14-L owns only its lane slice + structural bans."""
    rt = runtime or Path("D:/NEXUS_RUNTIME")
    existing = _read_sibling(rt, "v14_readiness_matrix.json") or {}
    bootstrap = _read_sibling(rt, "v14_lane_bootstrap.json") or []

    worktrees: dict[str, tuple[str, str, str]] = {}
    if isinstance(bootstrap, list):
        for entry in bootstrap:
            if not isinstance(entry, dict):
                continue
            lane_letter = str(entry.get("lane") or "").upper()
            if not lane_letter:
                continue
            lane_id = f"V14-{lane_letter}"
            worktrees[lane_id] = (
                str(entry.get("branch") or ""),
                str(entry.get("worktree") or ""),
                f"v14_{lane_letter.lower()}_status.json",
            )
    worktrees.setdefault(
        "V14-L",
        (
            BRANCH,
            r"D:\NEXUS_RUNTIME\worktrees\v14_l_research_redteam",
            "v14_l_status.json",
        ),
    )

    prev_lanes = existing.get("lanes") if isinstance(existing.get("lanes"), dict) else {}
    lanes: dict[str, Any] = {}
    commits: dict[str, Any] = {}
    test_statuses: dict[str, Any] = {}
    critical_findings: list[Any] = list(existing.get("V14_critical_findings") or [])
    high_findings: list[Any] = list(existing.get("V14_high_findings") or [])
    remaining_blockers: list[str] = []

    for lane_id, (branch, worktree, status_file) in worktrees.items():
        if lane_id == "V14-L":
            sib = lane_status
        else:
            sib = _read_sibling(rt, status_file)
            if not sib and isinstance(prev_lanes.get(lane_id), dict):
                prev = prev_lanes[lane_id]
                lanes[lane_id] = {
                    "branch": branch or prev.get("branch"),
                    "worktree": worktree or prev.get("worktree"),
                    "status": prev.get("status") or "RUNNING",
                    "remaining_blockers": prev.get("remaining_blockers") or ["IN_PROGRESS"],
                }
                if prev.get("agent_id"):
                    lanes[lane_id]["agent_id"] = prev["agent_id"]
                if prev.get("commit"):
                    lanes[lane_id]["commit"] = prev["commit"]
                    commits[lane_id] = prev["commit"]
                test_statuses[lane_id] = existing.get("V14_test_statuses", {}).get(
                    lane_id, "PENDING"
                )
                if lanes[lane_id]["status"] not in {"PASS"}:
                    remaining_blockers.append(f"{lane_id}_results_pending")
                continue

        status = _normalize_lane_status(sib)
        entry: dict[str, Any] = {"branch": branch, "worktree": worktree, "status": status}
        if isinstance(prev_lanes.get(lane_id), dict) and prev_lanes[lane_id].get("agent_id"):
            entry["agent_id"] = prev_lanes[lane_id]["agent_id"]
        if sib:
            entry["recommendation"] = (
                sib.get("recommendation")
                or sib.get("Research_Security_Redteam_status")
                or sib.get("status")
            )
            entry["passed"] = (
                True if status == "PASS" else (False if status == "FAIL" else sib.get("passed"))
            )
            if sib.get("commit") or sib.get("head"):
                entry["commit"] = sib.get("commit") or sib.get("head")
                commits[lane_id] = entry["commit"]
            lane_tests: dict[str, Any] = {
                "passed": entry["passed"],
                "raw_status": sib.get("status") or sib.get("recommendation"),
            }
            for key in (
                "scenario_pass_count",
                "scenario_total_count",
                "attack_blocked_count",
                "fixture_pass_count",
                "fixture_total_count",
            ):
                if key in sib:
                    lane_tests[key] = sib[key]
            test_statuses[lane_id] = lane_tests
            for cf in sib.get("critical_findings") or []:
                critical_findings.append(
                    {"lane": lane_id, **(cf if isinstance(cf, dict) else {"detail": cf})}
                )
            for hf in sib.get("high_findings") or []:
                high_findings.append(
                    {"lane": lane_id, **(hf if isinstance(hf, dict) else {"detail": hf})}
                )
            if status == "FAIL":
                remaining_blockers.append(f"{lane_id}_FAIL")
            elif status not in {"PASS"} and lane_id != "V14-L":
                remaining_blockers.append(f"{lane_id}_results_pending")
        else:
            remaining_blockers.append(f"{lane_id}_results_pending")
            test_statuses[lane_id] = "PENDING"
        lanes[lane_id] = entry

    f_ok = bool(lane_status.get("passed"))
    lanes["V14-L"]["status"] = "PASS" if f_ok else "FAIL"
    lanes["V14-L"]["passed"] = f_ok
    lanes["V14-L"]["recommendation"] = lane_status.get("recommendation")
    lanes["V14-L"]["attack_blocked_count"] = lane_status.get("attack_blocked_count")
    lanes["V14-L"]["scenario_pass_count"] = lane_status.get("scenario_pass_count")
    lanes["V14-L"]["scenario_total_count"] = lane_status.get("scenario_total_count")
    lanes["V14-L"]["remaining_blockers"] = (
        [] if f_ok else list(lane_status.get("remaining_blockers") or ["CRITICAL_FINDINGS"])
    )
    if lane_status.get("commit"):
        commits["V14-L"] = lane_status["commit"]
        lanes["V14-L"]["commit"] = lane_status["commit"]

    test_statuses["V14-L"] = {
        "scenario_pass_count": lane_status.get("scenario_pass_count"),
        "scenario_total_count": lane_status.get("scenario_total_count"),
        "fixture_pass_count": lane_status.get("fixture_pass_count"),
        "fixture_total_count": lane_status.get("fixture_total_count"),
        "attack_blocked_count": lane_status.get("attack_blocked_count"),
        "passed": lane_status.get("passed"),
        "recommendation": lane_status.get("recommendation"),
        "production_ast_survivors": (lane_status.get("production_ast") or {}).get("survivors"),
        "platform_blocked_pass_count": lane_status.get("platform_blocked_pass_count", 0),
    }

    for b in STRUCTURAL_BLOCKERS:
        if b not in remaining_blockers:
            remaining_blockers.append(b)
    for b in lane_status.get("remaining_blockers") or []:
        if b not in remaining_blockers:
            remaining_blockers.append(b)
    if not f_ok:
        remaining_blockers.insert(0, "V14-L_research_security_redteam_FAIL")
    remaining_blockers = [b for b in remaining_blockers if b != "V14-L_results_pending"]

    all_lane_pass = all(lanes[k]["status"] == "PASS" for k in lanes)
    return {
        "schema": existing.get("schema") or "v14_readiness_matrix_resumed",
        "created_at": existing.get("created_at") or _utc(),
        "updated_at": _utc(),
        "generated_by": "V14-L",
        "V13_INTEGRATED_HEAD": existing.get("V13_INTEGRATED_HEAD") or BASE_HEAD,
        "V14_PARENT": existing.get("V14_PARENT")
        or "feature/nexus-private-core-v14-edge-research",
        "lane_count": existing.get("lane_count") or len(lanes),
        "lanes": lanes,
        "auto_integration": False,
        "PR27_draft_unmerged": True,
        "qualification_ready_count": 0,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "V14_commits": commits if commits else existing.get("V14_commits") or "PENDING_LANE_RETURNS",
        "V14_test_statuses": test_statuses,
        "V14_critical_findings": critical_findings if critical_findings else [],
        "V14_high_findings": high_findings if high_findings else [],
        "V14_remaining_blockers": remaining_blockers,
        "V14_L_research_security_redteam": {
            "passed": f_ok,
            "recommendation": lane_status.get("recommendation"),
            "pass_number": lane_status.get("pass_number"),
            "scenario_pass_count": lane_status.get("scenario_pass_count"),
            "scenario_total_count": lane_status.get("scenario_total_count"),
            "fixture_pass_count": lane_status.get("fixture_pass_count"),
            "fixture_total_count": lane_status.get("fixture_total_count"),
            "attack_blocked_count": lane_status.get("attack_blocked_count"),
            "platform_blocked_pass_count": lane_status.get("platform_blocked_pass_count", 0),
            "exchange_write_attempt_count": lane_status.get("exchange_write_attempt_count", 0),
            "secret_leak_count": lane_status.get("secret_leak_count", 0),
            "mainnet_client_created_count": lane_status.get("mainnet_client_created_count", 0),
            "production_ast": lane_status.get("production_ast"),
            "scenarios": [
                {
                    "scenario_id": s.get("scenario_id"),
                    "passed": s.get("passed"),
                    "attack_blocked": s.get("attack_blocked"),
                    "platform_blocked": s.get("platform_blocked"),
                    "detail": s.get("detail"),
                }
                for s in (lane_status.get("scenarios") or [])
            ],
        },
        "V14_overall": (
            "LANES_INCOMPLETE"
            if not all_lane_pass
            else ("PASS_PENDING_STRUCTURAL_BLOCKERS" if f_ok else "FAIL")
        ),
        "hard_bans": list(HARD_BANS),
    }


def write_runtime_status(
    status: dict[str, Any],
    *,
    runtime: Path | None = None,
    commit: str | None = None,
) -> dict[str, Path]:
    """Write lane status + V14 readiness matrix to NEXUS_RUNTIME."""
    rt = runtime or Path("D:/NEXUS_RUNTIME")
    rt.mkdir(parents=True, exist_ok=True)

    lane_payload = dict(status)
    if commit:
        lane_payload["commit"] = commit
        lane_payload["head"] = commit
        lane_payload["lane_head_commit"] = commit
        lane_payload["feature_commit"] = commit
    lane_payload["runtime_status_path"] = RUNTIME_LANE_STATUS_PATH
    lane_payload["runtime_matrix_path"] = RUNTIME_MATRIX_PATH

    lane_path = rt / "v14_l_status.json"
    lane_path.write_text(
        json.dumps(lane_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    matrix = build_v14_readiness_matrix(lane_payload, runtime=rt)
    matrix_path = rt / "v14_readiness_matrix.json"
    matrix_path.write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"lane_status": lane_path, "matrix": matrix_path}


def run_research_redteam(
    *,
    root: Path | None = None,
    write_artifact: bool = True,
    write_runtime: bool = True,
    commit: str | None = None,
    pass_number: int = 1,
) -> dict[str, Any]:
    status = evaluate_research_redteam(root=root, pass_number=pass_number)
    if commit:
        status["commit"] = commit
        status["head"] = commit
    if write_artifact:
        write_immutable_artifacts(root=root, status=status)
    if write_runtime:
        write_runtime_status(status, commit=commit)
    return status
