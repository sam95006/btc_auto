#!/usr/bin/env python3
"""Founder R3 E/F remediation two-pass verification runner."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.review.r3_ef_remediation.probes import REMEDIATION_FINDING_IDS, run_pass1, run_pass2

ARTIFACT_REL = Path("artifacts/readiness/immutable/v11_1_r3_ef_remediation")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "UNKNOWN"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def main() -> int:
    out_dir = ROOT / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    pass1 = run_pass1()
    pass2 = run_pass2(pass1)

    findings = pass2["findings"]
    critical = [f for f in findings if f["status"] == "FAIL" and f["severity"] == "CRITICAL"]
    high = [f for f in findings if f["status"] == "FAIL" and f["severity"] == "HIGH"]
    passed = [f for f in findings if f["status"] == "PASS"]

    recommendation = {
        "schema": "v11_1_r3_ef_remediation_recommendation",
        "created_at": _utc(),
        "recommendation": pass2["recommendation"],
        "rationale": pass2["rationale"],
        "critical_open": pass2["critical_open"],
        "high_open": pass2["high_open"],
        "remediation_status": pass2["remediation_status"],
        "integration_gate": "CLEAR" if pass2["recommendation"] == "PASS_WITH_NOTES" else "HOLD",
        "lanes": {"E": "reflection_v23", "F": "point_in_time_qualification"},
        "hard_bans_preserved": {
            "lesson_gate": True,
            "promotion_blocked_ready": True,
            "no_merge_deploy_wf_oos_demo_exchange_mainnet_real_money": True,
        },
    }

    status = {
        "schema": "v11_1_r3_ef_remediation_status",
        "created_at": _utc(),
        "review": "FOUNDER_R3_EF_REMEDIATION",
        "branch": _git(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "git_head": _git(["git", "rev-parse", "HEAD"]),
        "base": "5b1d47543523f7e5be88da63256904171ce45165",
        "passes_completed": 2,
        "recommendation": pass2["recommendation"],
        "critical_fail_count": len(critical),
        "high_fail_count": len(high),
        "pass_count": len(passed),
        "stability_unstable_count": pass2["stability"]["unstable_count"],
        "remediation_finding_ids": list(REMEDIATION_FINDING_IDS),
        "remediation_status": pass2["remediation_status"],
    }

    summary = {
        "schema": "v11_1_r3_ef_remediation_summary",
        "created_at": _utc(),
        "status": status,
        "recommendation": recommendation,
        "pass1_fail_count": pass1["fail_count"],
        "pass2_critical_open": pass2["critical_open"],
        "pass2_high_open": pass2["high_open"],
        "remediation_status": pass2["remediation_status"],
        "key_findings": [
            {
                "finding_id": f["finding_id"],
                "severity": f["severity"],
                "status": f["status"],
                "title": f["title"],
            }
            for f in findings
        ],
    }

    _write(out_dir / "pass1_adversarial.json", pass1)
    _write(out_dir / "pass2_verification.json", pass2)
    _write(out_dir / "findings.json", {"findings": findings, "count": len(findings)})
    _write(out_dir / "recommendation.json", recommendation)
    _write(out_dir / "status.json", status)
    _write(out_dir / "summary.json", summary)
    _write(
        out_dir / "remediation_matrix.json",
        {
            "schema": "v11_1_r3_ef_remediation_matrix",
            "created_at": _utc(),
            "ids": pass2["remediation_status"],
            "all_fixed": all(v == "FIXED" for v in pass2["remediation_status"].values()),
        },
    )

    print(
        json.dumps(
            {
                "recommendation": pass2["recommendation"],
                "remediation_status": pass2["remediation_status"],
                "critical_open": pass2["critical_open"],
                "high_open": pass2["high_open"],
                "artifacts": str(out_dir),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if pass2["recommendation"] == "PASS_WITH_NOTES" else 2


if __name__ == "__main__":
    raise SystemExit(main())
