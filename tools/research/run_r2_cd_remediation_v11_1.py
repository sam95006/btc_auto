#!/usr/bin/env python3
"""Produce immutable R2-CD remediation artifacts (two-pass negative proofs).

Does not mutate .nexus_runtime/microstructure. Event Study remains NOT_READY.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.test_r2_cd_remediation_v11_1 import _run_pass  # noqa: E402

OUT = ROOT / "artifacts" / "readiness" / "immutable" / "v11_1_r2_cd_remediation"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True)
            .strip()
        )
    except Exception:
        return "UNKNOWN"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="r2_cd_remediation_") as td:
        tmp = Path(td)
        pass1 = _run_pass(tmp, "PASS_1")
        pass2 = _run_pass(tmp, "PASS_2")

    finding_ids = [
        "R2-C-001",
        "R2-C-002",
        "R2-D-001",
        "R2-C-005",
        "R2-D-002",
        "R2-D-004",
        "R2-C-003",
        "R2-C-004",
        "R2-C-006",
        "R2-D-003",
        "R2-D-005",
        "R2-C-007",
    ]
    matrix: dict[str, str] = {}
    for fid in ("R2-C-001", "R2-C-002", "R2-D-001", "R2-C-005", "R2-D-002", "R2-D-004"):
        s1 = pass1["scenarios"][fid]["status"]
        s2 = pass2["scenarios"][fid]["status"]
        matrix[fid] = "FIXED" if s1 == s2 == "FIXED" else "REMAINING"
    # Out-of-scope High/Medium left remaining (no scope creep).
    for fid in ("R2-C-003", "R2-C-004", "R2-C-006", "R2-D-003", "R2-D-005", "R2-C-007"):
        matrix[fid] = "REMAINING"

    critical_fixed = all(matrix[k] == "FIXED" for k in ("R2-C-001", "R2-C-002", "R2-D-001"))
    recommendation = (
        "CRITICAL_FIXED_PENDING_HIGH_HARDENING"
        if critical_fixed
        else "DO_NOT_INTEGRATE_AS_AUTHORITY_UNTIL_CRITICAL_FIXED"
    )

    status = {
        "schema": "v11_1_r2_cd_remediation_status_v1",
        "generated_at": _utc(),
        "head": _git_head(),
        "branch": "feature/v11_1-r2-cd-remediation",
        "base": "5b1d47543523f7e5be88da63256904171ce45165",
        "r2_review_agent": "c5ab8d19-c5a6-4cd4-83f6-aa8df0294dbc",
        "r2_recommendation_prior": "DO_NOT_INTEGRATE_AS_AUTHORITY_UNTIL_CRITICAL_FIXED",
        "integration_recommendation": recommendation,
        "critical_fixed": critical_fixed,
        "finding_matrix": matrix,
        "event_study_readiness_status": "NOT_READY",
        "raw_campaign_evidence_modified": False,
        "hard_bans": {
            "no_raw_microstructure_campaign_mutation": True,
            "no_event_study_ready_claim": True,
            "no_silent_repair": True,
            "cursor_native_only": True,
        },
        "pass1": {
            "all_critical_fixed": pass1["all_critical_fixed"],
            "hardened_fixed": pass1["hardened_fixed"],
        },
        "pass2": {
            "all_critical_fixed": pass2["all_critical_fixed"],
            "hardened_fixed": pass2["hardened_fixed"],
            "delta_vs_pass1_critical": 0 if pass1["all_critical_fixed"] == pass2["all_critical_fixed"] else 1,
        },
    }

    (OUT / "v11_1_r2_cd_remediation_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "finding_matrix.json").write_text(
        json.dumps({"generated_at": _utc(), "findings": matrix}, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / "adversarial_matrix_pass1.json").write_text(
        json.dumps(pass1, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "adversarial_matrix_pass2.json").write_text(
        json.dumps(pass2, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "event_study_readiness.json").write_text(
        json.dumps(
            {
                "schema": "event_study_readiness_v1",
                "event_study_readiness_status": "NOT_READY",
                "event_study_real_execution": False,
                "note": "R2-CD remediation must not start Event Study; readiness remains NOT_READY.",
                "created_at": _utc(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "README.md").write_text(
        "\n".join(
            [
                "# V11.1 R2-CD Remediation",
                "",
                f"Generated: `{status['generated_at']}`",
                f"HEAD: `{status['head']}`",
                "",
                "## Finding matrix",
                "",
                *[f"- **{k}** → `{v}`" for k, v in matrix.items()],
                "",
                f"## Recommendation: `{recommendation}`",
                "",
                "Event Study: **NOT_READY**. Raw campaign evidence untouched.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(json.dumps({"ok": critical_fixed, "recommendation": recommendation, "matrix": matrix}, indent=2))
    return 0 if critical_fixed else 1


if __name__ == "__main__":
    raise SystemExit(main())
