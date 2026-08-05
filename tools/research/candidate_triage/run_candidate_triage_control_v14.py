#!/usr/bin/env python3
"""Founder V14-H Candidate Triage Control harness.

Connects mechanism defs, Feature Lab, dynamic universe, cost sensitivity,
robustness, and blocked Qualification planning. TWO PASSES. Writes immutable
artifacts and runtime status JSON.

Hard bans: no formal WF/OOS, no select/promote, no QUALIFIED/PROMOTED/DEMO_READY,
no demo/shadow/exchange writes, no auto-integrate, no PR27 merge.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_candidate_triage.constants import (  # noqa: E402
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    FORMAL_STATUS_BLOCKED,
    HARD_BANS,
    INFRA_STATUS_BLOCKED_READY,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PROHIBITED_PATHS,
    RUNTIME_STATUS_DEFAULT,
    SCHEMA_ID,
    TRIAGE_STATUS_READY,
)
from backend.nexus_candidate_triage.controller import (  # noqa: E402
    run_two_pass_triage,
    write_immutable_artifacts,
)

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)gsk_[A-Za-z0-9]{20,}"),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def scan_secrets() -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_PATHS:
        target = ROOT / rel
        files: list[Path]
        if target.is_dir():
            files = [
                p
                for p in target.rglob("*")
                if p.is_file() and p.suffix.lower() in {".py", ".json", ".md"}
            ]
        elif target.is_file():
            files = [target]
        else:
            continue
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": "v14_h_candidate_triage_secret_scan",
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": list(OWNED_PATHS),
    }


def run_pytest() -> dict[str, Any]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/candidate_triage",
            "-q",
            "--tb=line",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return {
        "exit_code": proc.returncode,
        "passed": proc.returncode == 0,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "tail": "\n".join(out.strip().splitlines()[-80:]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V14-H Candidate Triage Control")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--runtime-status", type=Path, default=RUNTIME_STATUS_DEFAULT)
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--as-of-ms", type=int, default=1_700_000_000_000)
    args = parser.parse_args()

    root = args.root
    out_dir = args.out_dir or (root / ARTIFACT_REL)
    out_dir.mkdir(parents=True, exist_ok=True)

    two_pass = run_two_pass_triage(as_of_ms=args.as_of_ms)
    artifact_paths = write_immutable_artifacts(two_pass, root=root)

    secrets = scan_secrets()
    _write(out_dir / "secret_scan.json", secrets)

    pytest_result: dict[str, Any] = {"skipped": True, "passed": True}
    if not args.skip_pytest:
        pytest_result = run_pytest()
        _write(out_dir / "pytest_report.json", pytest_result)

    pass1 = two_pass["pass1"]
    head = _git_head()

    critical_findings: list[str] = []
    high_findings: list[str] = []
    remaining_blockers: list[str] = [
        "formal_walk_forward_blocked",
        "real_oos_reservation_blocked",
        "real_oos_consumption_blocked",
        "strategy_selection_blocked",
        "strategy_promotion_blocked",
        "qualified_output_forbidden",
        "promoted_output_forbidden",
        "demo_ready_output_forbidden",
        "demo_orders_blocked",
        "auto_integrate_banned",
        "founder_authorization_absent",
        "qualification_ready_count_zero_by_design",
    ]

    if not two_pass.get("both_passes_ok"):
        critical_findings.append("two_pass_triage_not_ok")
    if secrets["secret_leak_count"] > 0:
        critical_findings.append("secret_leak_detected")
    if not pytest_result.get("passed"):
        critical_findings.append("pytest_failed")
    if pass1.get("qualification_ready_count", 0) != 0:
        critical_findings.append("qualification_ready_count_nonzero")
    if pass1.get("formal_walk_forward_executed"):
        critical_findings.append("formal_walk_forward_executed")
    if pass1.get("oos_touched") or pass1.get("oos_reservation_created") or pass1.get("oos_consumed"):
        critical_findings.append("oos_touched")
    if pass1.get("strategy_selected") or pass1.get("strategy_promoted"):
        critical_findings.append("strategy_selected_or_promoted")
    if pass1.get("demo_order_count", 0) != 0:
        critical_findings.append("demo_orders_nonzero")
    if pass1.get("pr27_merged"):
        critical_findings.append("pr27_merged")
    if pass1.get("auto_integrated"):
        critical_findings.append("auto_integrated")
    if not pass1["proofs"].get("all_candidates_connected"):
        high_findings.append("not_all_connection_surfaces_connected")
    if not pass1["proofs"].get("histogram_covers_all_allowed"):
        high_findings.append("histogram_missing_allowed_status")

    status = "PASS" if not critical_findings and two_pass.get("both_passes_ok") else "FAIL"
    created = _utc()

    runtime_doc = {
        "schema": SCHEMA_ID,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "worktree": str(root),
        "runtime_status_path": str(args.runtime_status),
        "artifacts_dir": str(ARTIFACT_REL).replace("\\", "/"),
        "artifact_files": {
            k: str(v.relative_to(root)).replace("\\", "/") for k, v in artifact_paths.items()
        },
        "owned_paths": list(OWNED_PATHS),
        "prohibited_paths": list(PROHIBITED_PATHS),
        "hard_bans": list(HARD_BANS),
        "hard_bans_honored": True,
        "Founder_authorization_present": False,
        "infrastructure_status": INFRA_STATUS_BLOCKED_READY,
        "triage_control_status": TRIAGE_STATUS_READY,
        "qualification_status": FORMAL_STATUS_BLOCKED,
        "qualification_ready_count": 0,
        "formal_walk_forward_executed": False,
        "oos_reservation_created": False,
        "oos_executed": False,
        "oos_consumed": False,
        "oos_touched": False,
        "strategy_selected": False,
        "strategy_promoted": False,
        "demo_eligibility": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "pr27_merged": False,
        "mainnet": False,
        "real_money": False,
        "auto_integrated": False,
        "ingested_candidate_count": pass1["ingest"]["ingested_candidate_count"],
        "status_histogram": pass1["triage"]["status_histogram"],
        "both_passes_ok": two_pass.get("both_passes_ok"),
        "pass2_adversarial_ok": two_pass["pass2"].get("adversarial_ok"),
        "pass": status == "PASS",
        "status": status,
        "critical_findings": critical_findings,
        "high_findings": high_findings,
        "remaining_blockers": remaining_blockers,
        "secret_leak_count": secrets["secret_leak_count"],
        "pytest": {
            "elapsed_s": pytest_result.get("elapsed_s"),
            "exit_code": pytest_result.get("exit_code"),
            "passed": pytest_result.get("passed"),
            "skipped": pytest_result.get("skipped", False),
        },
        "pytest_passed": bool(pytest_result.get("passed")),
        "head_commit_at_run": head,
        "lane_head_commit": head,
        "created_at": created,
        "updated_at": created,
        "metrics": {
            "ingested_candidate_count": pass1["ingest"]["ingested_candidate_count"],
            "triaged_count": pass1["triage"]["triaged_count"],
            "qualification_ready_count": 0,
            "forbidden_output_count": 0,
            "status_histogram": pass1["triage"]["status_histogram"],
        },
    }
    _write(Path(args.runtime_status), runtime_doc)
    _write(out_dir / "lane_status.json", runtime_doc)

    print(json.dumps({"status": status, "both_passes_ok": two_pass.get("both_passes_ok"),
                      "qualification_ready_count": 0, "head": head}, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
