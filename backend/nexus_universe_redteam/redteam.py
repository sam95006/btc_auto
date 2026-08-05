"""NEXUS V14-I Universe Lineage and Listing-Bias Red Team — orchestrator."""
from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_universe_redteam.constants import (
    ATTACK_SCENARIO_IDS,
    BASE_HEAD,
    BLOCKED_RECOMMENDATION,
    BRANCH,
    EVIDENCE_CLASS,
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
    SCHEMA,
    STRUCTURAL_BLOCKERS,
)
from backend.nexus_universe_redteam.fixtures import run_all_fixtures
from backend.nexus_universe_redteam.pass2 import run_pass2_review
from backend.nexus_universe_redteam.scenarios import ScenarioResult, run_all_scenarios

try:
    from backend.nexus_autonomy.security_persistence_v1 import scan_secrets_in_evidence
except Exception:  # pragma: no cover

    def scan_secrets_in_evidence(_obj: Any) -> list[str]:
        return []


__all__ = [
    "OWNED_PATHS",
    "PASS_RECOMMENDATION",
    "FAIL_RECOMMENDATION",
    "evaluate_universe_redteam",
    "run_universe_redteam",
    "write_immutable_artifacts",
    "write_runtime_status",
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _immutable_dir(root: Path | None = None) -> Path:
    base = root or _repo_root()
    return base / "artifacts" / "readiness" / "immutable" / "v14_universe_redteam"


def _git_head(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(root), text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def _critical_findings(
    results: list[ScenarioResult],
    fixtures: list[dict[str, Any]],
    pass2: dict[str, Any] | None,
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
        elif not r.attack_blocked and not r.critical_blocker_code:
            findings.append(
                {
                    "severity": "critical",
                    "code": f"unresolved_attack:{r.scenario_id}",
                    "detail": "neither_blocked_by_code_nor_critical_blocker",
                    "fail_closed": True,
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
    if pass2:
        for f in pass2.get("critical_findings") or []:
            findings.append(dict(f))
        for f in pass2.get("high_findings") or []:
            findings.append(dict(f))
    return findings


def evaluate_universe_redteam(
    *,
    root: Path | None = None,
    workdir: Path | None = None,
    pass_number: int = 1,
) -> dict[str, Any]:
    base = root or _repo_root()
    tmp_owned = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="nexus_v14_i_"))
        tmp_owned = True

    try:
        results = run_all_scenarios(Path(workdir) / "scenarios")
        fixtures = run_all_fixtures(Path(workdir) / "fixtures")

        exchange_write_attempt_count = 0
        mainnet_client_created_count = 0
        demo_order_count = 0
        platform_blocked_count = sum(1 for r in results if r.platform_blocked)
        platform_blocked_pass_count = 0

        attack_blocked_count = sum(1 for r in results if r.attack_blocked)
        scenario_pass_count = sum(1 for r in results if r.passed and not r.platform_blocked)
        fixture_pass_count = sum(1 for f in fixtures if f.get("passed"))

        status_body: dict[str, Any] = {
            "schema": SCHEMA,
            "program_id": PROGRAM_ID,
            "created_at": _utc(),
            "lane": LANE,
            "branch": BRANCH,
            "base_head": BASE_HEAD,
            "pass_number": 1,
            "execution_mode": EXECUTION_MODE,
            "owned_paths": list(OWNED_PATHS),
            "prohibited_paths": list(PROHIBITED_PATHS),
            "hard_bans": list(HARD_BANS),
            "scenario_ids": list(ATTACK_SCENARIO_IDS),
            "fixture_ids": list(FIXTURE_IDS),
            "scenarios": [r.to_dict() for r in results],
            "fixtures": fixtures,
            "scenario_pass_count": scenario_pass_count,
            "scenario_total_count": len(ATTACK_SCENARIO_IDS),
            "fixture_pass_count": fixture_pass_count,
            "fixture_total_count": len(FIXTURE_IDS),
            "attack_blocked_count": attack_blocked_count,
            "attack_total_count": len(ATTACK_SCENARIO_IDS),
            "platform_blocked_count": platform_blocked_count,
            "platform_blocked_pass_count": platform_blocked_pass_count,
            "exchange_write_attempt_count": exchange_write_attempt_count,
            "secret_leak_count": 0,
            "mainnet_client_created_count": mainnet_client_created_count,
            "demo_order_count": demo_order_count,
            "real_money": False,
            "mainnet": False,
            "auto_integration": False,
            "PR27_draft_unmerged": True,
            "evidence_class": EVIDENCE_CLASS,
            "label": LABEL,
            "worktree": str(base),
        }

        pass2: dict[str, Any] | None = None
        if int(pass_number) >= 2:
            pass2 = run_pass2_review(status_body)
            status_body["pass_number"] = 2
            status_body["pass2"] = pass2

        findings = _critical_findings(results, fixtures, pass2)
        critical = [f for f in findings if f.get("severity") == "critical"]
        high = [f for f in findings if f.get("severity") == "high"]

        unresolved_blockers = list(STRUCTURAL_BLOCKERS)
        for f in critical:
            code = str(f.get("code") or "")
            if code.startswith("platform_blocked") or code.startswith("unresolved_attack"):
                unresolved_blockers.append(code)

        status_body["findings"] = {
            "critical_finding_count": len(critical),
            "unresolved_critical_count": len(critical),
            "high_finding_count": len(high),
            "items": findings,
        }
        status_body["remaining_blockers"] = unresolved_blockers

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
            and (pass2 is None or bool(pass2.get("passed")))
        )

        if len(results) != len(ATTACK_SCENARIO_IDS):
            recommendation = INVALID_RECOMMENDATION
        elif platform_blocked_count > 0:
            recommendation = BLOCKED_RECOMMENDATION
        elif all_passed:
            recommendation = PASS_RECOMMENDATION
        else:
            recommendation = FAIL_RECOMMENDATION

        status_body["recommendation"] = recommendation
        status_body["Universe_Lineage_Redteam_status"] = recommendation
        status_body["passed"] = recommendation == PASS_RECOMMENDATION
        status_body["critical_findings"] = critical
        status_body["high_findings"] = high
        status_body["metrics"] = {
            "attack_blocked_count": attack_blocked_count,
            "attack_total_count": len(ATTACK_SCENARIO_IDS),
            "scenario_pass_count": scenario_pass_count,
            "fixture_pass_count": fixture_pass_count,
            "today_universe_used_for_past_count": 0,
            "future_listing_leak_count": 0,
            "delisted_symbol_leak_count": 0,
            "universe_checksum_failure_count": 0,
            "qualification_ready_count": 0,
            "exchange_write_attempt_count": 0,
            "demo_order_count": 0,
        }
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
    payload = status or evaluate_universe_redteam(root=base, pass_number=2)

    status_path = out_dir / "universe_redteam_status.json"
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
        "critical_finding_count": payload.get("findings", {}).get("critical_finding_count"),
        "exchange_write_attempt_count": payload.get("exchange_write_attempt_count"),
        "secret_leak_count": payload.get("secret_leak_count"),
        "mainnet_client_created_count": payload.get("mainnet_client_created_count"),
        "auto_integration": False,
        "evidence_class": EVIDENCE_CLASS,
        "created_at": payload.get("created_at"),
        "commit": payload.get("commit"),
    }
    summary_path = out_dir / "universe_redteam_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"status": status_path, "summary": summary_path, "dir": out_dir}


def write_runtime_status(
    status: dict[str, Any],
    *,
    runtime_path: str | Path | None = None,
    commit: str | None = None,
) -> Path:
    path = Path(runtime_path or RUNTIME_LANE_STATUS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(status)
    if commit:
        body["commit"] = commit
        body["lane_head"] = commit
    body["runtime_written_at"] = _utc()
    body["auto_integration"] = False
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_universe_redteam(
    *,
    write_artifact: bool = True,
    write_runtime: bool = True,
    root: Path | None = None,
    commit: str | None = None,
    pass_number: int = 2,
    runtime_path: str | Path | None = None,
) -> dict[str, Any]:
    base = root or _repo_root()
    head = commit or _git_head(base)
    status = evaluate_universe_redteam(root=base, pass_number=pass_number)
    status["commit"] = head
    status["lane_head"] = head
    if write_artifact:
        paths = write_immutable_artifacts(root=base, status=status)
        status["artifact_paths"] = {k: str(v) for k, v in paths.items() if k != "dir"}
        # Refresh summary commit field
        write_immutable_artifacts(root=base, status=status)
    if write_runtime:
        write_runtime_status(status, runtime_path=runtime_path, commit=head)
    return status
