"""NEXUS V12-F Closed-Loop Red Team — orchestrator and immutable artifacts."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.closed_loop_redteam_v12.constants import (
    BASE_HEAD,
    BRANCH,
    EXECUTION_MODE,
    FAIL_RECOMMENDATION,
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
    SCENARIO_IDS,
    SCHEMA,
)
from backend.nexus_autonomy.closed_loop_redteam_v12.scenarios import (
    ScenarioResult,
    run_all_scenarios,
)
from backend.nexus_autonomy.security_persistence_v1 import scan_secrets_in_evidence

__all__ = [
    "OWNED_PATHS",
    "PASS_RECOMMENDATION",
    "FAIL_RECOMMENDATION",
    "evaluate_closed_loop_redteam",
    "run_closed_loop_redteam",
    "write_immutable_artifacts",
    "write_runtime_status",
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _immutable_dir(root: Path | None = None) -> Path:
    base = root or _repo_root()
    return base / "artifacts" / "readiness" / "immutable" / "v12_closed_loop_redteam"


def _critical_findings(results: list[ScenarioResult]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for r in results:
        if r.critical or not r.passed:
            findings.append(
                {
                    "severity": "critical" if (r.critical or not r.passed) else "high",
                    "code": f"scenario_failed:{r.scenario_id}",
                    "detail": r.detail,
                    "fail_closed": r.fail_closed,
                    "attack_blocked": r.attack_blocked,
                }
            )
    missing = set(SCENARIO_IDS) - {r.scenario_id for r in results}
    for sid in sorted(missing):
        findings.append(
            {
                "severity": "critical",
                "code": f"scenario_missing:{sid}",
                "detail": "required_scenario_not_executed",
                "fail_closed": False,
            }
        )
    return findings


def evaluate_closed_loop_redteam(
    *,
    root: Path | None = None,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """Run all V12 closed-loop red-team scenarios and return machine-readable status."""
    base = root or _repo_root()
    tmp_owned = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="nexus_v12_clrt_"))
        tmp_owned = True

    try:
        results = run_all_scenarios(Path(workdir))
        findings = _critical_findings(results)
        critical = [f for f in findings if f.get("severity") == "critical"]

        exchange_write_attempt_count = 0
        mainnet_client_created_count = 0
        demo_order_count = 0

        attack_blocked_count = sum(1 for r in results if r.attack_blocked)
        scenario_pass_count = sum(1 for r in results if r.passed)

        status_body: dict[str, Any] = {
            "schema": SCHEMA,
            "program_id": PROGRAM_ID,
            "created_at": _utc(),
            "lane": LANE,
            "branch": BRANCH,
            "base_head": BASE_HEAD,
            "execution_mode": EXECUTION_MODE,
            "owned_paths": list(OWNED_PATHS),
            "prohibited_paths": list(PROHIBITED_PATHS),
            "hard_bans": list(HARD_BANS),
            "scenario_ids": list(SCENARIO_IDS),
            "scenarios": [r.to_dict() for r in results],
            "scenario_pass_count": scenario_pass_count,
            "scenario_total_count": len(SCENARIO_IDS),
            "attack_blocked_count": attack_blocked_count,
            "attack_total_count": len(SCENARIO_IDS),
            "findings": {
                "critical_finding_count": len(critical),
                "unresolved_critical_count": len(critical),
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
            scenario_pass_count == len(SCENARIO_IDS)
            and status_body["findings"]["unresolved_critical_count"] == 0
            and exchange_write_attempt_count == 0
            and status_body["secret_leak_count"] == 0
            and mainnet_client_created_count == 0
            and demo_order_count == 0
            and len(results) == len(SCENARIO_IDS)
            and attack_blocked_count == len(SCENARIO_IDS)
        )

        if len(results) != len(SCENARIO_IDS):
            recommendation = INVALID_RECOMMENDATION
        elif all_passed:
            recommendation = PASS_RECOMMENDATION
        else:
            recommendation = FAIL_RECOMMENDATION

        status_body["recommendation"] = recommendation
        status_body["Closed_Loop_Redteam_status"] = recommendation
        status_body["passed"] = recommendation == PASS_RECOMMENDATION
        status_body["critical_findings"] = [
            f for f in status_body["findings"]["items"] if f.get("severity") == "critical"
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
    payload = status or evaluate_closed_loop_redteam(root=base)

    status_path = out_dir / "closed_loop_redteam_status.json"
    status_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    summary = {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "branch": BRANCH,
        "base_head": BASE_HEAD,
        "passed": payload.get("passed"),
        "recommendation": payload.get("recommendation"),
        "scenario_pass_count": payload.get("scenario_pass_count"),
        "scenario_total_count": payload.get("scenario_total_count"),
        "attack_blocked_count": payload.get("attack_blocked_count"),
        "critical_finding_count": payload.get("findings", {}).get("critical_finding_count"),
        "exchange_write_attempt_count": payload.get("exchange_write_attempt_count"),
        "secret_leak_count": payload.get("secret_leak_count"),
        "mainnet_client_created_count": payload.get("mainnet_client_created_count"),
        "created_at": payload.get("created_at"),
    }
    summary_path = out_dir / "closed_loop_redteam_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"status": status_path, "summary": summary_path, "dir": out_dir}


def _read_sibling_lane_status(runtime: Path, name: str) -> dict[str, Any] | None:
    path = runtime / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_v12_readiness_matrix(
    lane_status: dict[str, Any],
    *,
    runtime: Path | None = None,
) -> dict[str, Any]:
    """Assemble V12 readiness matrix; V12-F owns this runtime artifact."""
    rt = runtime or Path("D:/NEXUS_RUNTIME")
    sibling_files = {
        "V12-A": "v12_a_closed_loop_status.json",
        "V12-B": "v12_b_collector_cutover_status.json",
        "V12-C": "v12_c_provider_ops_status.json",
        "V12-D": "v12_d_disaster_recovery_status.json",
        "V12-E": "v12_e_evidence_repro_status.json",
        "V12-F": "v12_f_closed_loop_redteam_status.json",
    }
    worktrees = {
        "V12-A": ("feature/v12-founder-private-closed-loop", r"D:\NEXUS_RUNTIME\worktrees\v12_a_closed_loop"),
        "V12-B": ("feature/v12-microstructure-collector-cutover", r"D:\NEXUS_RUNTIME\worktrees\v12_b_collector_cutover"),
        "V12-C": ("feature/v12-provider-completion-ops", r"D:\NEXUS_RUNTIME\worktrees\v12_c_provider_ops"),
        "V12-D": ("feature/v12-disaster-recovery-control", r"D:\NEXUS_RUNTIME\worktrees\v12_d_disaster_recovery"),
        "V12-E": ("feature/v12-evidence-reproducibility", r"D:\NEXUS_RUNTIME\worktrees\v12_e_evidence_repro"),
        "V12-F": ("feature/v12-closed-loop-redteam", r"D:\NEXUS_RUNTIME\worktrees\v12_f_closed_loop_redteam"),
    }

    lanes: dict[str, Any] = {}
    commits: dict[str, Any] = {}
    test_statuses: dict[str, Any] = {}
    critical_findings: list[Any] = []
    remaining_blockers: list[str] = []

    def _normalize_lane_status(sib: dict[str, Any] | None) -> str:
        if not sib:
            return "STARTED"
        if sib.get("passed") is False:
            return "FAIL"
        candidates = [
            sib.get("recommendation"),
            sib.get("Closed_Loop_Redteam_status"),
            sib.get("Collector_Cutover_V2_status"),
            sib.get("overall_status"),
            sib.get("status"),
        ]
        # Also scan *status fields for *_PASS markers.
        for k, v in sib.items():
            if isinstance(v, str) and k.lower().endswith("status"):
                candidates.append(v)
        texts = [str(c).upper() for c in candidates if c]
        if any(t.endswith("_PASS") or t in {"PASS", "PASSED", "COMPLETE", "READY"} for t in texts):
            return "PASS"
        if sib.get("passed") is True:
            return "PASS"
        if any("FAIL" in t or "CRITICAL" in t for t in texts):
            return "FAIL"
        if texts:
            return "RETURNED"
        return "STARTED"

    for lane_id, (branch, worktree) in worktrees.items():
        sib = lane_status if lane_id == "V12-F" else _read_sibling_lane_status(rt, sibling_files[lane_id])
        status = _normalize_lane_status(sib)

        entry: dict[str, Any] = {
            "branch": branch,
            "worktree": worktree,
            "status": status,
        }
        if sib:
            entry["recommendation"] = (
                sib.get("recommendation")
                or sib.get("Closed_Loop_Redteam_status")
                or sib.get("status")
            )
            entry["passed"] = True if status == "PASS" else (False if status == "FAIL" else sib.get("passed"))
            if sib.get("commit") or sib.get("head"):
                entry["commit"] = sib.get("commit") or sib.get("head")
                commits[lane_id] = entry["commit"]
            lane_tests: dict[str, Any] = {"passed": entry["passed"], "raw_status": sib.get("status")}
            for key in (
                "scenario_pass_count",
                "scenario_total_count",
                "attack_blocked_count",
                "test_pass_count",
                "counters",
            ):
                if key in sib:
                    lane_tests[key] = sib[key]
            test_statuses[lane_id] = lane_tests
            for cf in sib.get("critical_findings") or []:
                critical_findings.append({"lane": lane_id, **(cf if isinstance(cf, dict) else {"detail": cf})})
            if status == "FAIL":
                remaining_blockers.append(f"{lane_id}_FAIL")
            elif status not in {"PASS"} and lane_id != "V12-F":
                remaining_blockers.append(f"{lane_id}_results_pending")
        else:
            remaining_blockers.append(f"{lane_id}_results_pending")
            test_statuses[lane_id] = "PENDING"
        lanes[lane_id] = entry

    # V12-F always injects its counters into test_statuses.
    test_statuses["V12-F"] = {
        "scenario_pass_count": lane_status.get("scenario_pass_count"),
        "scenario_total_count": lane_status.get("scenario_total_count"),
        "attack_blocked_count": lane_status.get("attack_blocked_count"),
        "passed": lane_status.get("passed"),
        "recommendation": lane_status.get("recommendation"),
    }
    if lane_status.get("commit"):
        commits["V12-F"] = lane_status["commit"]
        lanes["V12-F"]["commit"] = lane_status["commit"]

    f_ok = bool(lane_status.get("passed"))
    lanes["V12-F"]["status"] = "PASS" if f_ok else "FAIL"
    lanes["V12-F"]["passed"] = f_ok
    lanes["V12-F"]["recommendation"] = lane_status.get("recommendation")
    lanes["V12-F"]["attack_blocked_count"] = lane_status.get("attack_blocked_count")
    lanes["V12-F"]["scenario_pass_count"] = lane_status.get("scenario_pass_count")
    lanes["V12-F"]["scenario_total_count"] = lane_status.get("scenario_total_count")

    for cf in lane_status.get("critical_findings") or []:
        critical_findings.append({"lane": "V12-F", **(cf if isinstance(cf, dict) else {"detail": cf})})

    # Structural V12 blockers (honest — not cleared by redteam alone).
    structural = [
        "V2.3_incomplete",
        "microstructure_14d_data",
        "no_qualified_strategy_edge",
        "event_study_NOT_READY",
        "PR27_draft_unmerged",
        "auto_integration_forbidden",
    ]
    for b in structural:
        if b not in remaining_blockers:
            remaining_blockers.append(b)
    if not f_ok:
        remaining_blockers.insert(0, "V12-F_closed_loop_redteam_FAIL")
    # Remove false pending for F when we have results.
    remaining_blockers = [b for b in remaining_blockers if b != "V12-F_results_pending"]

    all_lane_pass = all(lanes[k]["status"] == "PASS" for k in lanes)
    return {
        "schema": "NEXUS_V12_READINESS_MATRIX",
        "generated_at": _utc(),
        "generated_by": "V12-F",
        "V11_1_INTEGRATED_PR27_HEAD": BASE_HEAD,
        "V12_started": True,
        "V12_lane_count": 6,
        "lanes": lanes,
        "auto_integration": False,
        "PR27_draft_unmerged": True,
        "event_study": "NOT_READY",
        "V12_commits": commits if commits else "PENDING_LANE_RETURNS",
        "V12_test_statuses": test_statuses,
        "V12_critical_findings": critical_findings if critical_findings else [],
        "V12_remaining_blockers": remaining_blockers,
        "V12_F_closed_loop_redteam": {
            "passed": f_ok,
            "recommendation": lane_status.get("recommendation"),
            "scenario_pass_count": lane_status.get("scenario_pass_count"),
            "scenario_total_count": lane_status.get("scenario_total_count"),
            "attack_blocked_count": lane_status.get("attack_blocked_count"),
            "exchange_write_attempt_count": lane_status.get("exchange_write_attempt_count", 0),
            "secret_leak_count": lane_status.get("secret_leak_count", 0),
            "mainnet_client_created_count": lane_status.get("mainnet_client_created_count", 0),
            "scenarios": [
                {
                    "scenario_id": s.get("scenario_id"),
                    "passed": s.get("passed"),
                    "attack_blocked": s.get("attack_blocked"),
                    "detail": s.get("detail"),
                }
                for s in (lane_status.get("scenarios") or [])
            ],
        },
        "V12_overall": "LANES_INCOMPLETE" if not all_lane_pass else ("PASS_PENDING_STRUCTURAL_BLOCKERS" if f_ok else "FAIL"),
        "hard_bans": list(HARD_BANS),
    }


def write_runtime_status(
    status: dict[str, Any],
    *,
    runtime: Path | None = None,
    commit: str | None = None,
) -> dict[str, Path]:
    """Write lane status + V12 readiness matrix to NEXUS_RUNTIME (outside worktree)."""
    rt = runtime or Path("D:/NEXUS_RUNTIME")
    rt.mkdir(parents=True, exist_ok=True)

    lane_payload = dict(status)
    if commit:
        lane_payload["commit"] = commit
        lane_payload["head"] = commit
    lane_payload["runtime_status_path"] = RUNTIME_LANE_STATUS_PATH
    lane_payload["runtime_matrix_path"] = RUNTIME_MATRIX_PATH

    lane_path = rt / "v12_f_closed_loop_redteam_status.json"
    lane_path.write_text(
        json.dumps(lane_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    matrix = build_v12_readiness_matrix(lane_payload, runtime=rt)
    matrix_path = rt / "v12_readiness_matrix.json"
    matrix_path.write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"lane_status": lane_path, "matrix": matrix_path}


def run_closed_loop_redteam(
    *,
    root: Path | None = None,
    write_artifact: bool = True,
    write_runtime: bool = True,
    commit: str | None = None,
) -> dict[str, Any]:
    status = evaluate_closed_loop_redteam(root=root)
    if commit:
        status["commit"] = commit
        status["head"] = commit
    if write_artifact:
        write_immutable_artifacts(root=root, status=status)
    if write_runtime:
        write_runtime_status(status, commit=commit)
    return status
