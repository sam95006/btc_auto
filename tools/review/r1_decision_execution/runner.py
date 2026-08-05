"""Two-pass FOUNDER R1 Decision + Execution review runner."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.review.r1_decision_execution.adversarial import run_adversarial_suite
from tools.review.r1_decision_execution.authority_scan import scan_authorities
from tools.review.r1_decision_execution.findings import build_findings
from tools.review.r1_decision_execution.lane_loader import resolve_lane_roots
from tools.review.r1_decision_execution.vocabulary import analyze_vocabulary


OWNED_PATHS = (
    "tools/review/r1_decision_execution/",
    "tests/review/test_r1_decision_execution_v11.py",
    "artifacts/readiness/immutable/v11_review_decision_execution/",
)

ARTIFACT_DIR = (
    Path(__file__).resolve().parents[3]
    / "artifacts"
    / "readiness"
    / "immutable"
    / "v11_review_decision_execution"
)

PASS_STATUS = "NEXUS_V11_REVIEW_DECISION_EXECUTION_COMPLETE"
SCHEMA = "v11_review_decision_execution"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_single_pass(pass_number: int, *, tmp: Path | None = None) -> dict[str, Any]:
    roots = resolve_lane_roots()
    work = Path(tmp) if tmp else Path(tempfile.mkdtemp(prefix=f"r1_pass{pass_number}_"))
    work.mkdir(parents=True, exist_ok=True)
    authority = scan_authorities(roots)
    vocabulary = analyze_vocabulary(roots)
    adversarial = run_adversarial_suite(work / "adv", roots)
    findings = build_findings(
        pass_number=pass_number,
        authority=authority,
        vocabulary=vocabulary,
        adversarial=adversarial,
    )
    return {
        "schema": SCHEMA,
        "pass_number": pass_number,
        "created_at": _utc(),
        "lane_a_branch": "feature/v11-decision-lifecycle-orchestrator",
        "lane_b_branch": "feature/v11-execution-microstructure-realism",
        "lane_a_head": "b6fcfe5c2391398d909c881e27ff9980177e7a21",
        "lane_b_head": "49076d7131b4802d9b997e7156dc3ba627ba1431",
        "lane_a_source": roots.lane_a_source,
        "lane_b_source": roots.lane_b_source,
        "authority": authority,
        "vocabulary": vocabulary,
        "adversarial": adversarial,
        "findings": findings,
    }


def run_r1_review(*, passes: int = 2, tmp: Path | None = None) -> dict[str, Any]:
    """Execute Pass 1 then Pass 2; Pass 2 re-validates and may refine classifications."""
    base = Path(tmp) if tmp else Path(tempfile.mkdtemp(prefix="r1_review_"))
    pass_reports: list[dict[str, Any]] = []
    for n in range(1, passes + 1):
        report = run_single_pass(n, tmp=base / f"pass_{n}")
        # Pass 2: mark any Pass-1 critical still present as confirmed; add
        # explicit bridge-absence confirmation from vocabulary+adversarial.
        if n == 2:
            f1 = pass_reports[0]["findings"]
            f2 = report["findings"]
            confirmed = {
                c["id"]
                for c in f1.get("critical_findings", [])
                if any(x.get("id") == c["id"] for x in f2.get("critical_findings", []))
            }
            report["pass2_confirmed_critical_ids"] = sorted(confirmed)
            report["pass2_delta"] = {
                "critical_count_pass1": f1.get("critical_count"),
                "critical_count_pass2": f2.get("critical_count"),
                "false_PASS_count_pass1": f1.get("false_PASS_count"),
                "false_PASS_count_pass2": f2.get("false_PASS_count"),
                "authority_conflict_count_pass1": f1.get("authority_conflict_count"),
                "authority_conflict_count_pass2": f2.get("authority_conflict_count"),
                "missing_negative_test_count_pass1": f1.get("missing_negative_test_count"),
                "missing_negative_test_count_pass2": f2.get("missing_negative_test_count"),
            }
        pass_reports.append(report)

    final = pass_reports[-1]["findings"]
    summary = {
        "schema": f"{SCHEMA}_summary",
        "package": "NEXUS_V11_REVIEW_DECISION_EXECUTION",
        "status": PASS_STATUS,
        "created_at": _utc(),
        "passes": passes,
        "false_PASS_count": final["false_PASS_count"],
        "authority_conflict_count": final["authority_conflict_count"],
        "missing_negative_test_count": final["missing_negative_test_count"],
        "critical_findings": final["critical_findings"],
        "high_findings": final["high_findings"],
        "critical_count": final["critical_count"],
        "high_count": final["high_count"],
        "integration_recommendation": final["integration_recommendation"],
        "owned_paths": list(OWNED_PATHS),
        "lane_a_modified": False,
        "lane_b_modified": False,
    }
    return {
        "summary": summary,
        "passes": pass_reports,
        "final_findings": final,
    }


def write_artifacts(out_dir: Path | None = None, *, report: dict[str, Any] | None = None) -> dict[str, Path]:
    out = Path(out_dir) if out_dir else ARTIFACT_DIR
    out.mkdir(parents=True, exist_ok=True)
    report = report or run_r1_review(passes=2)
    paths: dict[str, Path] = {}

    def _write(name: str, obj: object) -> Path:
        path = out / name
        path.write_text(
            json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        paths[name] = path
        return path

    _write("review_summary.json", report["summary"])
    _write("final_findings.json", report["final_findings"])
    for p in report["passes"]:
        n = int(p["pass_number"])
        _write(f"pass_{n}_report.json", p)
        _write(f"pass_{n}_findings.json", p["findings"])
        _write(f"pass_{n}_adversarial.json", p["adversarial"])
        _write(f"pass_{n}_authority.json", p["authority"])
        _write(f"pass_{n}_vocabulary.json", p["vocabulary"])

    # Machine-readable return matrix for the coordinator.
    matrix = {
        "schema": f"{SCHEMA}_return_matrix",
        "created_at": _utc(),
        "false_PASS_count": report["summary"]["false_PASS_count"],
        "authority_conflict_count": report["summary"]["authority_conflict_count"],
        "missing_negative_test_count": report["summary"]["missing_negative_test_count"],
        "critical_findings": [c.get("id") for c in report["summary"]["critical_findings"]],
        "high_findings": [h.get("id") for h in report["summary"]["high_findings"]],
        "critical_findings_detail": report["summary"]["critical_findings"],
        "high_findings_detail": report["summary"]["high_findings"],
        "integration_recommendation": report["summary"]["integration_recommendation"],
    }
    _write("return_matrix.json", matrix)

    blockers = {
        "schema": f"{SCHEMA}_blockers",
        "created_at": _utc(),
        "integration_recommendation": report["summary"]["integration_recommendation"],
        "blockers": [
            {
                "id": c.get("id"),
                "severity": "critical",
                "detail": c.get("detail"),
                "remediation_hint": (
                    "Require Decision↔Intent↔Position bridge + cross-lifecycle CI invariants "
                    "before treating Lane A+B as jointly integrable."
                ),
            }
            for c in report["summary"]["critical_findings"]
        ],
    }
    _write("BLOCKERS.json", blockers)

    md_lines = [
        "# V11 R1 Decision + Execution Review",
        "",
        f"Generated: {report['summary']['created_at']}",
        "",
        "## Return matrix",
        "",
        f"- false_PASS_count: **{report['summary']['false_PASS_count']}**",
        f"- authority_conflict_count: **{report['summary']['authority_conflict_count']}**",
        f"- missing_negative_test_count: **{report['summary']['missing_negative_test_count']}**",
        f"- critical_count: **{report['summary']['critical_count']}**",
        f"- high_count: **{report['summary']['high_count']}**",
        f"- integration_recommendation: **{report['summary']['integration_recommendation']}**",
        "",
        "## Critical findings",
        "",
    ]
    for c in report["summary"]["critical_findings"]:
        md_lines.append(f"- `{c.get('id')}` — {c.get('detail')}")
    md_lines.extend(["", "## High findings", ""])
    for h in report["summary"]["high_findings"]:
        md_lines.append(f"- `{h.get('id')}` — {h.get('detail')}")
    md_lines.extend(
        [
            "",
            "## Policy",
            "",
            "- Reviewer-owned paths only",
            "- Lane A/B implementation paths untouched",
            "- No Draft PR if gh missing",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(md_lines), encoding="utf-8")
    paths["SUMMARY.md"] = out / "SUMMARY.md"
    return paths
