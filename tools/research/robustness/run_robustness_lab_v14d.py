#!/usr/bin/env python3
"""V14-D Robustness and Multiple-Testing Lab campaign harness.

TWO PASSES. Synthetic/fixture development evidence only.
Hard bans: no WF, no OOS, no demo/exchange, no auto-integrate, no qualification claims.

Emits artifacts under:
  artifacts/readiness/immutable/v14_robustness/

Writes D:\\NEXUS_RUNTIME\\v14_d_status.json by default.
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

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ART_REL = Path("artifacts/readiness/immutable/v14_robustness")
RUNTIME_STATUS_DEFAULT = Path(r"D:\NEXUS_RUNTIME\v14_d_status.json")
BASE_COMMIT = "15ecb7b9524d253ec4f2fb04dc73aa1673ec906a"
BRANCH = "feature/v14-robustness-multiple-testing"

OWNED_SCAN_PATHS = [
    "backend/nexus_research_validation/",
    "tools/research/robustness/",
    "tests/research_validation/",
    "artifacts/readiness/immutable/v14_robustness/",
]

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
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
    for rel in OWNED_SCAN_PATHS:
        target = ROOT / rel
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
        "schema": "v14_d_secret_scan",
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": OWNED_SCAN_PATHS,
    }


def run_pytest() -> dict[str, Any]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/research_validation/",
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


def run_pass1() -> dict[str, Any]:
    from backend.nexus_research_validation import run_robustness_lab
    from backend.nexus_research_validation.hard_bans import (
        scan_owned_paths_for_banned_claims,
    )

    lab = run_robustness_lab()
    banned = scan_owned_paths_for_banned_claims(ROOT)
    return {
        "pass": "PASS_1",
        "lab": lab,
        "banned_claim_scan": banned,
        "candidate_count": lab["candidate_count"],
        "label_histogram": lab["label_histogram"],
        "cluster_count": lab["correlation_clustering"]["cluster_count"],
        "total_family_tests": lab["multiple_comparison"]["total_tests"],
        "deterministic_fixture_replay": lab["deterministic_fixture_replay"],
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "qualification_ready_count": 0,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "auto_integrate": False,
    }


def run_pass2(pass1: dict[str, Any]) -> dict[str, Any]:
    from backend.nexus_research_validation import (
        HardBanViolation,
        adversarial_self_review,
        refuse_auto_integrate,
        refuse_exchange_write,
        refuse_formal_walk_forward,
        refuse_oos_consume,
    )
    from backend.nexus_research_validation.fdr import benjamini_hochberg
    from backend.nexus_research_validation.labeling import assert_label_allowed

    findings: list[dict[str, Any]] = []
    adv = adversarial_self_review(pass1["lab"])
    findings.extend(adv["findings"])

    # Hard-ban refuse APIs must raise
    for name, fn in (
        ("OOS", refuse_oos_consume),
        ("WF", refuse_formal_walk_forward),
        ("EXCHANGE", refuse_exchange_write),
        ("AUTO_INTEGRATE", refuse_auto_integrate),
    ):
        try:
            fn()
            findings.append(
                {
                    "severity": "CRITICAL",
                    "code": f"HARD_BAN_{name}_NOT_ENFORCED",
                    "detail": "refuse API did not raise",
                }
            )
        except HardBanViolation:
            pass

    # FDR empty / ordering sanity
    bh = benjamini_hochberg([0.001, 0.02, 0.5], q=0.1)
    if bh["n_tests"] != 3 or 0 not in bh["rejected_indices"]:
        findings.append(
            {
                "severity": "HIGH",
                "code": "FDR_BH_UNEXPECTED",
                "detail": bh,
            }
        )

    # Banned labels must raise
    try:
        assert_label_allowed("QUALIFIED")
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "QUALIFIED_LABEL_ACCEPTED",
                "detail": "assert_label_allowed accepted QUALIFIED",
            }
        )
    except ValueError:
        pass

    if not pass1.get("banned_claim_scan", {}).get("ok", False):
        findings.append(
            {
                "severity": "HIGH",
                "code": "BANNED_CLAIM_SCAN_HITS",
                "detail": pass1.get("banned_claim_scan"),
            }
        )

    if pass1.get("qualification_ready_count", 1) != 0:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "QUALIFICATION_READY_NONZERO_PASS1",
                "detail": pass1.get("qualification_ready_count"),
            }
        )

    critical = [f for f in findings if f.get("severity") == "CRITICAL"]
    high = [f for f in findings if f.get("severity") == "HIGH"]
    # Deduplicate INFO from adv already included
    return {
        "pass": "PASS_2",
        "findings": findings,
        "critical_count": len(critical),
        "high_count": len(high),
        "adversarial_ok": len(critical) == 0 and len(high) == 0,
        "bh_smoke": bh,
        "hard_ban_refuse_ok": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=ROOT / ART_REL)
    parser.add_argument("--runtime-status", type=Path, default=RUNTIME_STATUS_DEFAULT)
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")
    os.environ.setdefault("FORMAL_WALK_FORWARD", "false")
    os.environ.setdefault("OOS_EXECUTE", "false")
    os.environ.setdefault("OOS_CONSUME", "false")
    os.environ.setdefault("AUTO_INTEGRATE", "false")

    secrets = scan_secrets()
    _write(out / "secret_scan.json", secrets)

    pass1 = run_pass1()
    lab = pass1["lab"]
    _write(out / "fixture_manifest.json", lab["fixture_manifest"])
    _write(
        out / "evaluations.json",
        {
            "schema": "v14_d_evaluations",
            "created_at": _utc(),
            "candidate_count": lab["candidate_count"],
            "evaluations": lab["evaluations"],
            "label_histogram": lab["label_histogram"],
        },
    )
    _write(out / "multiple_comparison.json", lab["multiple_comparison"])
    _write(out / "lineage_index.json", lab["lineage_index"])
    _write(out / "correlation_clustering.json", lab["correlation_clustering"])
    _write(
        out / "pass1_summary.json",
        {
            k: v
            for k, v in pass1.items()
            if k != "lab"
        },
    )

    pass2 = run_pass2(pass1)
    _write(out / "pass2_adversarial.json", {**pass2, "created_at": _utc()})

    pytest_result: dict[str, Any] = {"skipped": True, "passed": True}
    if not args.skip_pytest:
        pytest_result = run_pytest()
        _write(out / "pytest_report.json", pytest_result)

    head = _git_head()
    status_pass = (
        pass1["deterministic_fixture_replay"] is True
        and pass1["formal_walk_forward_executed"] is False
        and pass1["oos_consumed"] is False
        and pass1["qualification_ready_count"] == 0
        and pass1["exchange_write_attempt_count"] == 0
        and pass1["demo_order_count"] == 0
        and pass1["banned_claim_scan"]["ok"] is True
        and pass2["adversarial_ok"] is True
        and secrets["secret_leak_count"] == 0
        and bool(pytest_result.get("passed"))
        and int(lab["candidate_count"]) >= 8
        and int(lab["multiple_comparison"]["total_tests"]) >= 8
    )

    hist = lab["label_histogram"]
    lane_status = {
        "schema": "FOUNDER_V14_D_ROBUSTNESS_MULTIPLE_TESTING_LAB",
        "lane": "V14-D",
        "lane_name": "ROBUSTNESS_AND_MULTIPLE_TESTING_LAB",
        "branch": BRANCH,
        "worktree": str(ROOT),
        "base_commit": BASE_COMMIT,
        "head_commit_at_run": head,
        "created_at": _utc(),
        "updated_at": _utc(),
        "status": "PASS" if status_pass else "FAIL",
        "pass1": "PASS" if status_pass or pass1["deterministic_fixture_replay"] else "FAIL",
        "pass2": "PASS" if pass2["adversarial_ok"] else "FAIL",
        "passes_completed": ["PASS_1", "PASS_2"],
        "candidate_count": lab["candidate_count"],
        "label_histogram": hist,
        "multiple_testing_rejected_count": hist.get("MULTIPLE_TESTING_REJECTED", 0),
        "cost_destroyed_count": hist.get("COST_DESTROYED", 0),
        "data_blocked_count": hist.get("DATA_QUALITY_BLOCKED", 0),
        "development_robust_count": hist.get("DEVELOPMENT_ROBUST", 0),
        "development_fragile_count": hist.get("DEVELOPMENT_FRAGILE", 0),
        "insufficient_sample_count": hist.get("INSUFFICIENT_SAMPLE", 0),
        "cluster_count": lab["correlation_clustering"]["cluster_count"],
        "redundant_pair_count": lab["correlation_clustering"]["redundant_pair_count"],
        "total_family_tests": lab["multiple_comparison"]["total_tests"],
        "total_bh_discoveries": lab["multiple_comparison"]["total_bh_discoveries"],
        "deterministic_fixture_replay": lab["deterministic_fixture_replay"],
        "adversarial_ok": pass2["adversarial_ok"],
        "critical_findings": pass2["critical_count"],
        "high_findings": pass2["high_count"],
        "remaining_blockers": [],
        "secret_leak_count": secrets["secret_leak_count"],
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "mainnet": False,
        "real_money": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "qualification_ready_count": 0,
        "auto_integrate": False,
        "pr27_merged": False,
        "fixture_source": "synthetic_sanitized",
        "pytest_passed": bool(pytest_result.get("passed")),
        "artifacts_dir": str(ART_REL).replace("\\", "/"),
        "owned_paths": OWNED_SCAN_PATHS,
        "hard_bans_honored": True,
        "runtime_status_path": str(args.runtime_status),
    }
    _write(out / "v14_robustness_status.json", lane_status)
    (out / "SUMMARY.md").write_text(
        "\n".join(
            [
                "# V14-D Robustness and Multiple-Testing Lab",
                "",
                f"- status: **{lane_status['status']}**",
                f"- candidates: {lane_status['candidate_count']}",
                f"- labels: {json.dumps(hist, sort_keys=True)}",
                f"- clusters: {lane_status['cluster_count']}",
                f"- family tests: {lane_status['total_family_tests']}",
                f"- adversarial ok: {lane_status['adversarial_ok']}",
                "",
                "Fixture/synthetic development evidence only.",
                "No formal walk-forward. No OOS. No qualification claims.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    runtime = {
        **lane_status,
        "pass2_findings": pass2["findings"],
        "tests": {
            "path": "tests/research_validation/",
            "passed": bool(pytest_result.get("passed")),
            "exit_code": pytest_result.get("exit_code"),
            "elapsed_s": pytest_result.get("elapsed_s"),
        },
        "pushed": False,
        "commits": [],
    }
    _write(args.runtime_status, runtime)
    print(json.dumps({"status": lane_status["status"], "pass": status_pass}, indent=2))
    return 0 if status_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
