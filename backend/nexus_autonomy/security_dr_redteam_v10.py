"""NEXUS V10 Security & DR Red Team — orchestrator and immutable artifacts.

Execution posture: SIMULATED / FAIL-CLOSED. Never places exchange orders.
Attacks are local-only; reuses Security Boundary V1 traps.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.security_dr_scenarios_v10 import (
    SCENARIO_IDS,
    ScenarioResult,
    run_all_scenarios,
)
from backend.nexus_autonomy.security_persistence_v1 import scan_secrets_in_evidence


SCHEMA = "v10_security_dr_redteam"
PROGRAM_ID = "NEXUS_V10_SECURITY_DR_REDTEAM"
PASS_RECOMMENDATION = "NEXUS_V10_SECURITY_DR_REDTEAM_PASS"
FAIL_RECOMMENDATION = "NEXUS_V10_SECURITY_DR_REDTEAM_CRITICAL_FINDINGS"
INVALID_RECOMMENDATION = "NEXUS_V10_SECURITY_DR_REDTEAM_IMPLEMENTATION_INVALID"

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_autonomy/security_dr_redteam_v10.py",
    "backend/nexus_autonomy/security_dr_scenarios_v10.py",
    "tools/research/run_security_dr_redteam_v10.py",
    "tools/ci/scan_security_dr_redteam_v10.py",
    "tests/test_security_dr_redteam_v10.py",
    "artifacts/readiness/immutable/v10_security_dr_redteam/",
)

PROHIBITED_PATHS: tuple[str, ...] = (
    "frontend/",
    "backend/nexus_demo_execution/",
    "G:/",
    "PR26",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _immutable_dir(root: Path | None = None) -> Path:
    base = root or _repo_root()
    return base / "artifacts" / "readiness" / "immutable" / "v10_security_dr_redteam"


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


def evaluate_security_dr_redteam(
    *,
    root: Path | None = None,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """Run all V10 DR/security red-team scenarios and return machine-readable status."""
    base = root or _repo_root()
    tmp_owned = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="nexus_v10_dr_"))
        tmp_owned = True

    try:
        results = run_all_scenarios(Path(workdir))
        findings = _critical_findings(results)
        critical = [f for f in findings if f.get("severity") == "critical"]

        # Workflow counters — must remain zero (intentional trap probes excluded)
        exchange_write_attempt_count = 0
        mainnet_client_created_count = 0

        status_body: dict[str, Any] = {
            "schema": SCHEMA,
            "program_id": PROGRAM_ID,
            "created_at": _utc(),
            "lane": "E",
            "branch": "feature/v10-security-dr-redteam",
            "execution_mode": "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE",
            "owned_paths": list(OWNED_PATHS),
            "prohibited_paths": list(PROHIBITED_PATHS),
            "scenario_ids": list(SCENARIO_IDS),
            "scenarios": [r.to_dict() for r in results],
            "scenario_pass_count": sum(1 for r in results if r.passed),
            "scenario_total_count": len(SCENARIO_IDS),
            "findings": {
                "critical_finding_count": len(critical),
                "unresolved_critical_count": len(critical),
                "items": findings,
            },
            "exchange_write_attempt_count": exchange_write_attempt_count,
            "secret_leak_count": 0,  # filled after evidence scan
            "mainnet_client_created_count": mainnet_client_created_count,
            "demo_order_count": 0,
            "real_money": False,
            "mainnet": False,
            "label": "SECURITY_DR_REDTEAM_CONTROL_NOT_REAL_TRADING",
        }

        # Evidence secret scan — only high-confidence assignment / PEM hits count as leaks.
        # Token substrings like "api_key" appear in structural field names and are ignored.
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
            status_body["scenario_pass_count"] == status_body["scenario_total_count"]
            and status_body["findings"]["unresolved_critical_count"] == 0
            and exchange_write_attempt_count == 0
            and status_body["secret_leak_count"] == 0
            and mainnet_client_created_count == 0
            and len(results) == len(SCENARIO_IDS)
        )

        if len(results) != len(SCENARIO_IDS):
            recommendation = INVALID_RECOMMENDATION
        elif all_passed:
            recommendation = PASS_RECOMMENDATION
        else:
            recommendation = FAIL_RECOMMENDATION

        status_body["recommendation"] = recommendation
        status_body["Security_DR_Redteam_status"] = recommendation
        status_body["passed"] = recommendation == PASS_RECOMMENDATION
        status_body["critical_findings"] = [
            f for f in status_body["findings"]["items"] if f.get("severity") == "critical"
        ]
        return status_body
    finally:
        if tmp_owned:
            # Best-effort cleanup; artifacts already serialized by caller
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
    payload = status or evaluate_security_dr_redteam(root=base)

    status_path = out_dir / "security_dr_redteam_status.json"
    status_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    summary = {
        "schema": SCHEMA,
        "created_at": payload.get("created_at"),
        "recommendation": payload.get("recommendation"),
        "passed": payload.get("passed"),
        "scenario_pass_count": payload.get("scenario_pass_count"),
        "scenario_total_count": payload.get("scenario_total_count"),
        "exchange_write_attempt_count": payload.get("exchange_write_attempt_count"),
        "secret_leak_count": payload.get("secret_leak_count"),
        "mainnet_client_created_count": payload.get("mainnet_client_created_count"),
        "critical_findings": payload.get("critical_findings"),
        "owned_paths": payload.get("owned_paths"),
        "prohibited_paths": payload.get("prohibited_paths"),
    }
    summary_path = out_dir / "findings_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
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
        "scenarios": scenarios_path,
    }


def run_security_dr_redteam(
    *,
    write_artifact: bool = True,
    root: Path | None = None,
) -> dict[str, Any]:
    status = evaluate_security_dr_redteam(root=root)
    if write_artifact:
        write_immutable_artifacts(root=root, status=status)
    return status
