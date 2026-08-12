#!/usr/bin/env python3
"""Founder R3 two-pass Reflection + Qualification review runner."""
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

from tools.review.r3_reflection_qualification.origin_loader import REVIEW_ARTIFACT_REL
from tools.review.r3_reflection_qualification.probes import run_pass1, run_pass2

INSPECT_SURFACE = [
    "provider_retry_authority",
    "checkpoint_schema_authority",
    "completed_case_dedupe",
    "critic_ordering",
    "classification_taxonomy",
    "lesson_gate",
    "point_in_time_provenance",
    "future_data_exclusion",
    "oos_seal",
    "promotion_blocking",
]

ADVERSARIAL_SCENARIOS = [
    "429_as_quality_failure",
    "critic_before_reasoner",
    "completed_case_replay",
    "checkpoint_counter_drift",
    "undetermined_process_lost",
    "future_timestamp_nested",
    "oos_seal_regenerated",
    "founder_authorization_spoofed",
    "lesson_while_v23_incomplete",
]


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
    out_dir = ROOT / REVIEW_ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    pass1 = run_pass1()
    pass2 = run_pass2(pass1)

    findings = pass2["findings"]
    critical = [f for f in findings if f["status"] == "FAIL" and f["severity"] == "CRITICAL"]
    high = [f for f in findings if f["status"] == "FAIL" and f["severity"] == "HIGH"]
    passed = [f for f in findings if f["status"] == "PASS"]

    recommendation = {
        "schema": "v11_review_reflection_qualification_recommendation",
        "created_at": _utc(),
        "recommendation": pass2["recommendation"],
        "rationale": pass2["rationale"],
        "critical_open": pass2["critical_open"],
        "high_open": pass2["high_open"],
        "integration_gate": "FAIL_CLOSED" if pass2["recommendation"] == "BLOCK_INTEGRATION" else "HOLD",
        "lanes": {
            "E": "feature/v11-reflection-v23-adjudication",
            "F": "feature/v11-point-in-time-qualification",
        },
    }

    status = {
        "schema": "v11_review_reflection_qualification_status",
        "created_at": _utc(),
        "review": "FOUNDER_R3_REFLECTION_QUALIFICATION",
        "branch": _git(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "git_head": _git(["git", "rev-parse", "HEAD"]),
        "base": "e4f30f9b8abaaade6151a75ef5ac6face53d5135",
        "passes_completed": 2,
        "recommendation": pass2["recommendation"],
        "critical_fail_count": len(critical),
        "high_fail_count": len(high),
        "pass_count": len(passed),
        "stability_unstable_count": pass2["stability"]["unstable_count"],
        "inspect_surface": INSPECT_SURFACE,
        "adversarial_scenarios": ADVERSARIAL_SCENARIOS,
    }

    summary = {
        "schema": "v11_review_reflection_qualification_summary",
        "created_at": _utc(),
        "status": status,
        "recommendation": recommendation,
        "pass1_fail_count": pass1["fail_count"],
        "pass2_critical_open": pass2["critical_open"],
        "pass2_high_open": pass2["high_open"],
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

    print(
        json.dumps(
            {
                "recommendation": pass2["recommendation"],
                "critical_open": pass2["critical_open"],
                "high_open": pass2["high_open"],
                "artifacts": str(out_dir),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if pass2["recommendation"] != "BLOCK_INTEGRATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
