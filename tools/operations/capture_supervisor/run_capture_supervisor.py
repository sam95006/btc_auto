#!/usr/bin/env python3
"""V14-A Live Capture Integrity Supervisor runner (observe/recommend only).

Hard bans: no V13-A collector modification, no live stop execution, no Event Study,
no exchange write / Demo / Shadow / mainnet / PR27 merge / auto-integrate.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME"))


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head(repo: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_changed_owned(repo: Path) -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain"], text=True
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    owned_prefixes = (
        "backend/nexus_capture_supervisor/",
        "tools/operations/capture_supervisor/",
        "tests/capture_supervisor/",
        "artifacts/readiness/immutable/v14_capture_supervisor/",
    )
    files: list[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if any(path == p.rstrip("/") or path.startswith(p) for p in owned_prefixes):
            files.append(path)
    return sorted(set(files))


def main() -> int:
    parser = argparse.ArgumentParser(description="V14-A capture integrity supervisor")
    parser.add_argument("--runtime", default=str(RUNTIME))
    parser.add_argument("--disk-root", default="D:\\")
    parser.add_argument("--campaign-id", default="ms_accum_v13_integrity_14d")
    parser.add_argument(
        "--velocity-sample-seconds",
        type=float,
        default=2.0,
        help="Storage velocity sample window (keep small for CI; live runs may raise)",
    )
    parser.add_argument(
        "--artifact-dir",
        default=None,
        help="Override artifact output directory",
    )
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()

    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    sys.path.insert(0, str(ROOT))

    from backend.nexus_capture_supervisor.adversarial import run_adversarial_pass2
    from backend.nexus_capture_supervisor.constants import (
        ARTIFACT_REL,
        BASE_COMMIT,
        BRANCH,
        EVENT_STUDY_MUST_REMAIN,
        HARD_BANS,
        LANE,
        OWNED_PATHS,
        RUNTIME_STATUS_NAME,
        SCHEMA_BOTH,
        SCHEMA_PASS1,
        SCHEMA_STATUS,
    )
    from backend.nexus_capture_supervisor.secret_scan import secret_scan
    from backend.nexus_capture_supervisor.supervisor import CaptureIntegritySupervisor
    from backend.nexus_capture_supervisor.util import atomic_write_json

    runtime = Path(args.runtime)
    art_dir = Path(args.artifact_dir) if args.artifact_dir else (ROOT / ARTIFACT_REL)
    work = ROOT / ".nexus_runtime" / "capture_supervisor" / "adversarial"
    work.mkdir(parents=True, exist_ok=True)

    supervisor = CaptureIntegritySupervisor(
        runtime_root=runtime,
        disk_root=args.disk_root,
        campaign_id=args.campaign_id,
        velocity_sample_seconds=float(args.velocity_sample_seconds),
    )
    observation = supervisor.observe()

    live = bool((observation.get("path_meta") or {}).get("live_capture_started"))
    evidence_class = "REAL_LIVE_CAMPAIGN_READONLY" if live else "SYNTHETIC_FIXTURE"

    pytest_report: dict[str, Any] = {"skipped": True}
    if not args.skip_pytest:
        pytest_report = _run_pytest(ROOT)

    pass1 = {
        "schema": SCHEMA_PASS1,
        "lane": LANE,
        "pass": 1,
        "created_at": _utc(),
        "all_passed": bool(pytest_report.get("passed", False))
        or bool(args.skip_pytest and observation.get("integrity_status")),
        "evidence_class": evidence_class,
        "observation": observation,
        "pytest": pytest_report,
        "metrics": _metrics(observation),
        "event_study_readiness_status": EVENT_STUDY_MUST_REMAIN,
        "exchange_write_attempt_count": 0,
        "collector_modified": False,
    }
    # Pass1 requires observation produced + tests if run
    if not args.skip_pytest:
        pass1["all_passed"] = bool(pytest_report.get("passed")) and observation.get("schema") is not None
    else:
        pass1["all_passed"] = observation.get("schema") is not None

    changed = _git_changed_owned(ROOT)
    pass2 = run_adversarial_pass2(
        repo_root=ROOT,
        work_root=work,
        pass1=pass1,
        changed_files=changed,
    )
    secret = secret_scan(ROOT)

    both = {
        "schema": SCHEMA_BOTH,
        "lane": LANE,
        "created_at": _utc(),
        "pass1": pass1,
        "pass2": pass2,
        "secret_scan": secret,
        "all_passed": bool(pass1.get("all_passed"))
        and bool(pass2.get("all_passed"))
        and int(secret.get("secret_leak_count") or 0) == 0,
        "hard_bans": list(HARD_BANS),
        "owned_paths": list(OWNED_PATHS),
        "auto_integrate": False,
        "event_study_readiness_status": EVENT_STUDY_MUST_REMAIN,
    }

    git_head = _git_head(ROOT)
    status = {
        "schema": SCHEMA_STATUS,
        "lane": LANE,
        "lane_name": "LIVE_CAPTURE_INTEGRITY_SUPERVISOR",
        "created_at": _utc(),
        "branch": BRANCH,
        "base_head": BASE_COMMIT,
        "git_head": git_head,
        "campaign_id": args.campaign_id,
        "evidence_class": evidence_class,
        "pass1_all_passed": pass1.get("all_passed"),
        "pass2_all_passed": pass2.get("all_passed"),
        "both_passes_ok": both.get("all_passed"),
        "integrity_status": observation.get("integrity_status"),
        "process_status": (observation.get("process_liveness") or {}).get("status"),
        "ws_status": (observation.get("ws_health") or {}).get("status"),
        "safe_stop_required": (observation.get("recommendations") or {}).get("safe_stop_required"),
        "safe_stop_executed": False,
        "restart_recommended": (observation.get("recommendations") or {}).get("restart_recommended"),
        "restart_executed": False,
        "metrics": _metrics(observation),
        "critical_findings": observation.get("critical_findings") or [],
        "high_findings": observation.get("high_findings") or [],
        "blockers": _blockers(both, observation, secret),
        "secret_leak_count": secret.get("secret_leak_count"),
        "event_study_readiness_status": EVENT_STUDY_MUST_REMAIN,
        "event_study_real_execution": False,
        "exchange_write_attempt_count": 0,
        "demo_used": False,
        "mainnet_used": False,
        "shadow_used": False,
        "PR27_merged": False,
        "collector_modified": False,
        "auto_integration": False,
        "owned_paths_only": True,
        "readiness": "PASS" if both.get("all_passed") else "FAIL",
        "changed_files": changed,
    }

    art_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "capture_supervisor_status.json": status,
        "pass1_observation.json": pass1,
        "pass2_adversarial.json": pass2,
        "both_passes.json": both,
        "observation.json": observation,
        "recommendations.json": observation.get("recommendations"),
        "secret_scan.json": secret,
        "pytest_report.json": pytest_report,
        "metrics.json": _metrics(observation),
        "readiness_summary.json": {
            "schema": "v14_a_capture_supervisor_readiness_summary",
            "lane": LANE,
            "readiness": status["readiness"],
            "both_passes_ok": both.get("all_passed"),
            "integrity_status": observation.get("integrity_status"),
            "critical_count": len(status["critical_findings"]),
            "high_count": len(status["high_findings"]),
            "blockers": status["blockers"],
            "created_at": _utc(),
        },
    }
    for name, payload in payloads.items():
        atomic_write_json(art_dir / name, payload)

    # Runtime status for founder matrix (outside repo — allowed)
    runtime_status = {
        **status,
        "artifact_dir": str(art_dir),
        "runtime_root": str(runtime),
        "updated_at": _utc(),
    }
    atomic_write_json(runtime / RUNTIME_STATUS_NAME, runtime_status)

    print(json.dumps({"readiness": status["readiness"], "git_head": git_head, "artifact_dir": str(art_dir)}, indent=2))
    return 0 if both.get("all_passed") else 1


def _metrics(observation: dict[str, Any]) -> dict[str, Any]:
    part = observation.get("partition_accounting") or {}
    storage = observation.get("storage") or {}
    vel = storage.get("velocity") or {}
    ck = observation.get("ws_health") or {}
    return {
        "partition_count": part.get("partition_count"),
        "sealed_count": part.get("sealed_count"),
        "open_tail_count": part.get("open_tail_count"),
        "symbol_count": part.get("symbol_count"),
        "missing_hours": part.get("missing_hours"),
        "campaign_bytes": storage.get("campaign_bytes"),
        "free_gib": storage.get("free_gib"),
        "bytes_per_second": vel.get("bytes_per_second"),
        "trade_count": ck.get("trade_count"),
        "liq_count": ck.get("liq_count"),
        "process_status": (observation.get("process_liveness") or {}).get("status"),
        "ws_status": ck.get("status"),
        "integrity_status": observation.get("integrity_status"),
        "safe_stop_required": (observation.get("recommendations") or {}).get("safe_stop_required"),
    }


def _blockers(both: dict[str, Any], observation: dict[str, Any], secret: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not both.get("all_passed"):
        if not (both.get("pass1") or {}).get("all_passed"):
            blockers.append("pass1_failed")
        if not (both.get("pass2") or {}).get("all_passed"):
            blockers.append("pass2_failed")
    if int(secret.get("secret_leak_count") or 0) > 0:
        blockers.append("secret_leak")
    for f in observation.get("critical_findings") or []:
        blockers.append(f"critical:{f.get('code')}")
    return blockers


def _run_pytest(repo: Path) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/capture_supervisor",
        "-q",
        "--tb=line",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(repo), "EXCHANGE_WRITE": "false"},
            check=False,
        )
    except OSError as exc:
        return {"passed": False, "error": f"{type(exc).__name__}:{exc}"}
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


if __name__ == "__main__":
    raise SystemExit(main())
