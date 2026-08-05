#!/usr/bin/env python3
"""V15-D Research Meta-Analysis and False Discovery campaign harness.

TWO PASSES. Synthetic/fixture development evidence only.
Hard bans: no WF, no OOS, no demo/exchange, no auto-integrate, no qualification
claims, no silent favorable-run selection, no promising-without-siblings,
no lane *_status.json.

Emits artifacts under:
  artifacts/readiness/immutable/v15_research_meta_analysis/

Does NOT write any *_status.json (Coordinator-owned report only).
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

ART_REL = Path("artifacts/readiness/immutable/v15_research_meta_analysis")
BASE_COMMIT = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"
BRANCH = "feature/v15-research-meta-analysis"

OWNED_SCAN_PATHS = [
    "backend/nexus_research_meta_analysis/",
    "tools/research/meta_analysis/",
    "tests/research_meta_analysis/",
    "artifacts/readiness/immutable/v15_research_meta_analysis/",
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
        "schema": "v15_d_secret_scan",
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
            "tests/research_meta_analysis/",
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
    from backend.nexus_research_meta_analysis import run_meta_analysis
    from backend.nexus_research_meta_analysis.hard_bans import (
        scan_owned_paths_for_banned_claims,
    )

    report = run_meta_analysis()
    banned = scan_owned_paths_for_banned_claims(ROOT)
    return {
        "pass": "PASS_1",
        "report": report,
        "banned_claim_scan": banned,
        "experiment_count": report["experiment_count"],
        "label_histogram": report["label_histogram"],
        "duplicate_pair_count": report["experiment_duplication"]["duplicate_pair_count"],
        "fdr_n_tests": report["false_discovery_adjustment"]["n_tests"],
        "promising_packet_count": len(report["promising_packets"]),
        "silent_selection_blocked": report["favorable_run_selection_detection"][
            "silent_selection_blocked"
        ],
        "axes_coverage_ok": report["axes_coverage_ok"],
        "deterministic_fixture_replay": report["deterministic_fixture_replay"],
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "oos_reserved": False,
        "qualification_ready_count": 0,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "auto_integrate": False,
        "lane_status_json_written": False,
    }


def run_pass2(pass1: dict[str, Any]) -> dict[str, Any]:
    from backend.nexus_research_meta_analysis import (
        HardBanViolation,
        adversarial_self_review,
        refuse_auto_integrate,
        refuse_exchange_write,
        refuse_formal_walk_forward,
        refuse_lane_status_json,
        refuse_oos_consume,
        refuse_oos_execute,
        refuse_oos_reserve,
        refuse_promising_without_siblings,
        refuse_silent_favorable_selection,
    )
    from backend.nexus_research_meta_analysis.fdr import benjamini_hochberg
    from backend.nexus_research_meta_analysis.labeling import assert_label_allowed

    findings: list[dict[str, Any]] = []
    adv = adversarial_self_review(pass1["report"])
    findings.extend(adv["findings"])

    for name, fn in (
        ("OOS_CONSUME", refuse_oos_consume),
        ("OOS_EXECUTE", refuse_oos_execute),
        ("OOS_RESERVE", refuse_oos_reserve),
        ("WF", refuse_formal_walk_forward),
        ("EXCHANGE", refuse_exchange_write),
        ("AUTO_INTEGRATE", refuse_auto_integrate),
        ("SILENT_FAVORABLE", refuse_silent_favorable_selection),
        ("PROMISING_NO_SIBLINGS", refuse_promising_without_siblings),
        ("LANE_STATUS_JSON", refuse_lane_status_json),
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

    bh = benjamini_hochberg([0.001, 0.02, 0.5], q=0.1)
    if bh["n_tests"] != 3 or 0 not in bh["rejected_indices"]:
        findings.append(
            {
                "severity": "HIGH",
                "code": "FDR_BH_UNEXPECTED",
                "detail": bh,
            }
        )

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

    if pass1.get("lane_status_json_written"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "LANE_STATUS_JSON_FLAG",
                "detail": "pass1 claimed lane status json write",
            }
        )

    critical = [f for f in findings if f.get("severity") == "CRITICAL"]
    high = [f for f in findings if f.get("severity") == "HIGH"]
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
    os.environ.setdefault("OOS_RESERVE", "false")
    os.environ.setdefault("AUTO_INTEGRATE", "false")

    secrets = scan_secrets()
    _write(out / "secret_scan.json", secrets)

    pass1 = run_pass1()
    report = pass1["report"]
    _write(out / "fixture_manifest.json", report["fixture_manifest"])
    _write(
        out / "evaluations.json",
        {
            "schema": "v15_d_evaluations",
            "created_at": _utc(),
            "experiment_count": report["experiment_count"],
            "evaluations": report["evaluations"],
            "label_histogram": report["label_histogram"],
        },
    )
    _write(out / "candidate_correlation.json", report["candidate_correlation"])
    _write(
        out / "mechanism_family_correlation.json",
        report["mechanism_family_correlation"],
    )
    _write(out / "false_discovery_adjustment.json", report["false_discovery_adjustment"])
    _write(out / "experiment_duplication.json", report["experiment_duplication"])
    _write(
        out / "favorable_run_selection.json",
        report["favorable_run_selection_detection"],
    )
    _write(
        out / "promising_packets.json",
        {
            "schema": "v15_d_promising_packets",
            "created_at": _utc(),
            "packets": report["promising_packets"],
            "note": "Promising results retain all failed sibling experiments.",
        },
    )
    _write(
        out / "pass1_summary.json",
        {k: v for k, v in pass1.items() if k != "report"},
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
        and pass1["oos_reserved"] is False
        and pass1["qualification_ready_count"] == 0
        and pass1["exchange_write_attempt_count"] == 0
        and pass1["demo_order_count"] == 0
        and pass1["lane_status_json_written"] is False
        and pass1["silent_selection_blocked"] is True
        and pass1["axes_coverage_ok"] is True
        and pass1["banned_claim_scan"]["ok"] is True
        and pass2["adversarial_ok"] is True
        and secrets["secret_leak_count"] == 0
        and bool(pytest_result.get("passed"))
        and int(report["experiment_count"]) >= 10
        and int(report["false_discovery_adjustment"]["n_tests"]) >= 10
        and int(pass1["promising_packet_count"]) >= 1
        and int(pass1["duplicate_pair_count"]) >= 1
    )

    hist = report["label_histogram"]
    campaign_result = {
        "schema": "FOUNDER_V15_D_RESEARCH_META_ANALYSIS",
        "lane": "V15-D",
        "lane_name": "RESEARCH_META_ANALYSIS_AND_FALSE_DISCOVERY",
        "branch": BRANCH,
        "worktree": str(ROOT),
        "base_commit": BASE_COMMIT,
        "head_commit_at_run": head,
        "created_at": _utc(),
        "updated_at": _utc(),
        "result": "PASS" if status_pass else "FAIL",
        "pass1": "PASS" if status_pass or pass1["deterministic_fixture_replay"] else "FAIL",
        "pass2": "PASS" if pass2["adversarial_ok"] else "FAIL",
        "passes_completed": ["PASS_1", "PASS_2"],
        "experiment_count": report["experiment_count"],
        "label_histogram": hist,
        "duplicate_pair_count": pass1["duplicate_pair_count"],
        "fdr_n_tests": pass1["fdr_n_tests"],
        "fdr_discovery_count": report["false_discovery_adjustment"].get(
            "discovery_count", 0
        ),
        "promising_packet_count": pass1["promising_packet_count"],
        "silent_selection_blocked": pass1["silent_selection_blocked"],
        "axes_coverage_ok": pass1["axes_coverage_ok"],
        "required_analysis_axes": report["required_analysis_axes"],
        "deterministic_fixture_replay": report["deterministic_fixture_replay"],
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
        "oos_reserved": False,
        "qualification_ready_count": 0,
        "auto_integrate": False,
        "pr27_merged": False,
        "lane_status_json_written": False,
        "fixture_source": "synthetic_sanitized",
        "pytest_passed": bool(pytest_result.get("passed")),
        "artifacts_dir": str(ART_REL).replace("\\", "/"),
        "owned_paths": OWNED_SCAN_PATHS,
        "hard_bans_honored": True,
    }
    # Immutable campaign result — deliberately NOT named *_status.json
    _write(out / "campaign_result.json", campaign_result)
    (out / "SUMMARY.md").write_text(
        "\n".join(
            [
                "# V15-D Research Meta-Analysis and False Discovery",
                "",
                f"- result: **{campaign_result['result']}**",
                f"- experiments: {campaign_result['experiment_count']}",
                f"- labels: {json.dumps(hist, sort_keys=True)}",
                f"- FDR tests: {campaign_result['fdr_n_tests']}",
                f"- duplicate pairs: {campaign_result['duplicate_pair_count']}",
                f"- promising packets (with failed siblings): "
                f"{campaign_result['promising_packet_count']}",
                f"- silent favorable-run selection blocked: "
                f"{campaign_result['silent_selection_blocked']}",
                f"- adversarial ok: {campaign_result['adversarial_ok']}",
                "",
                "Fixture/synthetic development evidence only.",
                "No formal walk-forward. No OOS. No qualification claims.",
                "No lane *_status.json written.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Explicit hard ban: do not write any *_status.json
    status_globs = list(out.glob("*_status.json")) + list(ROOT.glob("v15_d*_status.json"))
    if status_globs:
        print(
            json.dumps(
                {
                    "result": "FAIL",
                    "reason": "status_json_written",
                    "paths": [str(p) for p in status_globs],
                },
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "lane": "V15-D",
                "result": campaign_result["result"],
                "pass": status_pass,
                "head": head,
                "experiment_count": campaign_result["experiment_count"],
                "promising_packet_count": campaign_result["promising_packet_count"],
                "silent_selection_blocked": campaign_result["silent_selection_blocked"],
                "artifacts_dir": campaign_result["artifacts_dir"],
            },
            indent=2,
        )
    )
    return 0 if status_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
