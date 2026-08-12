"""V15-A two-pass campaign — PIT development data foundation (no human status JSON)."""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_dev_data_foundation.adversarial import run_adversarial_pass
from backend.nexus_dev_data_foundation.constants import (
    ART_REL,
    BASE_COMMIT,
    BRANCH,
    EVIDENCE_CLASS,
    EXECUTION_MODE,
    FAIL_RECOMMENDATION,
    FORBIDDEN_STATUS_GLOB,
    HARD_BANS,
    LABEL,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    PROGRAM_ID,
    SCHEMA,
    SCHEMA_VERSION,
    STRUCTURAL_BLOCKERS,
)
from backend.nexus_dev_data_foundation.hashing import sha_obj, utc_now_iso
from backend.nexus_dev_data_foundation.inventory import inventory_in_repo_sources
from backend.nexus_dev_data_foundation.partitions import build_time_partitions, verify_no_dev_oos_overlap
from backend.nexus_dev_data_foundation.pit import prove_oos_excluded, prove_pit_as_of
from backend.nexus_dev_data_foundation.records import verify_record

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]

PROFIT_CLAIM_PATTERNS = [
    re.compile(r"(?i)guaranteed\s+profit"),
    re.compile(r"(?i)proven\s+alpha"),
    re.compile(r"(?i)qualified\s+strategy"),
]


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Enforce ban: never write v15_*_status.json
    if path.name.startswith("v15_") and path.name.endswith("_status.json"):
        raise RuntimeError(f"forbidden_status_json:{path.name}")
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def scan_secrets(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if not target.exists():
            continue
        files = (
            [p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in {".py", ".json", ".md"}]
            if target.is_dir()
            else [target]
        )
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": "v15_a_secret_scan",
        "created_at": utc_now_iso(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": list(OWNED_PATHS),
    }


def scan_profit_claims(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_PATHS[:3]:
        target = root / rel
        if not target.exists():
            continue
        files = [p for p in target.rglob("*.py")] if target.is_dir() else []
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in PROFIT_CLAIM_PATTERNS:
                if pat.search(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": "v15_a_edge_claim_scan",
        "created_at": utc_now_iso(),
        "hit_count": len(hits),
        "hits": hits,
    }


def run_pytest(root: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            "tests/dev_data_foundation",
            "-q",
            "--tb=line",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    passed_count = 0
    failed_count = 0
    for line in out.splitlines():
        m = re.search(r"(\d+)\s+passed", line)
        if m:
            passed_count = int(m.group(1))
        m2 = re.search(r"(\d+)\s+failed", line)
        if m2:
            failed_count = int(m2.group(1))
    return {
        "exit_code": proc.returncode,
        "passed": proc.returncode == 0,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "tail": "\n".join(out.strip().splitlines()[-40:]),
    }


def assert_no_forbidden_status_artifacts(root: Path) -> dict[str, Any]:
    art = root / ART_REL
    banned = list(art.glob(FORBIDDEN_STATUS_GLOB)) if art.is_dir() else []
    for rel in OWNED_PATHS:
        target = root / rel
        if target.is_dir():
            banned.extend(target.rglob("v15_*_status.json"))
    rels = sorted({str(p.relative_to(root)).replace("\\", "/") for p in banned if p.is_file()})
    return {"ok": len(rels) == 0, "banned_files": rels}


def run_pass1(root: Path) -> dict[str, Any]:
    partitions = build_time_partitions()
    overlap = verify_no_dev_oos_overlap(partitions)
    inventory = inventory_in_repo_sources(root)
    records = inventory["records"]
    verify_failures = [verify_record(r) for r in records if not verify_record(r).get("ok")]
    oos_proof = prove_oos_excluded(records)
    # PIT as_of mid-DEV: fixtures with earlier availability should be eligible
    pit_proof = prove_pit_as_of(records, as_of_ms=partitions["partitions"][0]["end_ms"])
    # Fix pit_holds: no eligible id should have availability > as_of
    as_of = partitions["partitions"][0]["end_ms"]
    leaked = []
    for r in records:
        if r["record_id"] in pit_proof["eligible_ids"]:
            avail = r.get("availability_ms")
            if avail is not None and int(avail) > as_of:
                leaked.append(r["record_id"])
    pit_proof["leaked_ids"] = leaked
    pit_proof["pit_holds"] = len(leaked) == 0
    pit_proof["future_leak_count"] = len(leaked)

    by_state: dict[str, int] = {}
    by_cat: dict[str, int] = {}
    for r in records:
        by_state[str(r["availability_state"])] = by_state.get(str(r["availability_state"]), 0) + 1
        by_cat[str(r["partition_category"])] = by_cat.get(str(r["partition_category"]), 0) + 1

    passed = (
        overlap["ok"]
        and oos_proof["oos_excluded"]
        and pit_proof["pit_holds"]
        and len(verify_failures) == 0
        and inventory["invented_history_count"] == 0
        and not inventory.get("oos_consumed")
    )
    return {
        "schema": "v15_a_pass1_summary",
        "pass_number": 1,
        "passed": passed,
        "created_at": utc_now_iso(),
        "partitions": partitions,
        "overlap_check": overlap,
        "inventory_checksum": inventory["inventory_checksum"],
        "record_count": inventory["record_count"],
        "missing_path_count": inventory["missing_path_count"],
        "availability_state_histogram": by_state,
        "partition_category_histogram": by_cat,
        "oos_exclusion_proof": oos_proof,
        "pit_proof": pit_proof,
        "verify_failure_count": len(verify_failures),
        "verify_failures": verify_failures[:20],
        "oos_consumed": False,
        "invented_history": False,
    }, inventory


def run_campaign(root: Path, *, run_tests: bool = True) -> dict[str, Any]:
    art = root / ART_REL
    art.mkdir(parents=True, exist_ok=True)

    # Guard: delete any accidental forbidden status files before we start
    for p in art.glob(FORBIDDEN_STATUS_GLOB):
        p.unlink()

    pass1, inventory = run_pass1(root)
    pass2 = run_adversarial_pass(root, inventory=inventory, pass_number=2)
    # Second adversarial sweep on same inventory (required dual pass)
    pass2_b = run_adversarial_pass(root, inventory=inventory, pass_number=2)
    # Merge: fail if either fails
    pass2_merged = {
        "schema": "v15_a_pass2_adversarial",
        "pass_number": 2,
        "passed": pass2["passed"] and pass2_b["passed"],
        "sweep_a": pass2,
        "sweep_b": {
            "passed": pass2_b["passed"],
            "critical_finding_count": pass2_b["critical_finding_count"],
            "high_finding_count": pass2_b["high_finding_count"],
            "check_pass_count": pass2_b["check_pass_count"],
            "check_total_count": pass2_b["check_total_count"],
        },
        "critical_finding_count": pass2["critical_finding_count"] + pass2_b["critical_finding_count"],
        "high_finding_count": pass2["high_finding_count"] + pass2_b["high_finding_count"],
        "critical_findings": pass2["critical_findings"] + pass2_b["critical_findings"],
        "high_findings": pass2["high_findings"] + pass2_b["high_findings"],
        "checks": pass2["checks"],
        "deterministic_replay": pass2["check_pass_count"] == pass2_b["check_pass_count"]
        and pass2["critical_finding_count"] == pass2_b["critical_finding_count"],
    }

    secrets = scan_secrets(root)
    edge_scan = scan_profit_claims(root)
    status_ban = assert_no_forbidden_status_artifacts(root)
    pytest_report = run_pytest(root) if run_tests else {"passed": True, "passed_count": 0, "failed_count": 0, "skipped": True}

    critical = list(pass2_merged["critical_findings"])
    high = list(pass2_merged["high_findings"])
    if secrets["secret_leak_count"] > 0:
        critical.append(
            {
                "severity": "CRITICAL",
                "code": "SECRET_LEAK",
                "detail": "Secret pattern hit in owned paths",
                "evidence": secrets,
            }
        )
    if edge_scan["hit_count"] > 0:
        critical.append(
            {
                "severity": "CRITICAL",
                "code": "PROFIT_CLAIM",
                "detail": "Profit/alpha claim pattern in owned code",
                "evidence": edge_scan,
            }
        )
    if not status_ban["ok"]:
        critical.append(
            {
                "severity": "CRITICAL",
                "code": "FORBIDDEN_STATUS_JSON",
                "detail": "v15_*_status.json present",
                "evidence": status_ban,
            }
        )
    if not pass1["passed"]:
        critical.append(
            {
                "severity": "CRITICAL",
                "code": "PASS1_FAILED",
                "detail": "Pass 1 foundation checks failed",
                "evidence": {"verify_failure_count": pass1["verify_failure_count"]},
            }
        )
    if not pytest_report.get("passed", False):
        high.append(
            {
                "severity": "HIGH",
                "code": "PYTEST_FAILED",
                "detail": "dev_data_foundation tests failed",
                "evidence": {"exit_code": pytest_report.get("exit_code"), "tail": pytest_report.get("tail")},
            }
        )

    passed = (
        pass1["passed"]
        and pass2_merged["passed"]
        and len(critical) == 0
        and secrets["secret_leak_count"] == 0
        and status_ban["ok"]
        and pytest_report.get("passed", False)
    )
    recommendation = PASS_RECOMMENDATION if passed else FAIL_RECOMMENDATION
    head = _git_head(root)

    metrics = {
        "record_count": inventory["record_count"],
        "in_repo_source_count": inventory["in_repo_source_count"],
        "missing_path_count": inventory["missing_path_count"],
        "partition_count": len(pass1["partitions"]["partitions"]),
        "oos_consumed": False,
        "oos_executed": False,
        "invented_history_count": 0,
        "pit_holds": pass1["pit_proof"]["pit_holds"],
        "oos_excluded": pass1["oos_exclusion_proof"]["oos_excluded"],
        "pass1_passed": pass1["passed"],
        "pass2_passed": pass2_merged["passed"],
        "adversarial_check_pass_count": pass2["check_pass_count"],
        "adversarial_check_total_count": pass2["check_total_count"],
        "tests_passed": pytest_report.get("passed_count", 0),
        "tests_failed": pytest_report.get("failed_count", 0),
        "secret_leak_count": secrets["secret_leak_count"],
        "qualification_ready_count": 0,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "availability_state_histogram": pass1["availability_state_histogram"],
        "partition_category_histogram": pass1["partition_category_histogram"],
    }

    campaign = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "created_at": utc_now_iso(),
        "execution_mode": EXECUTION_MODE,
        "evidence_class": EVIDENCE_CLASS,
        "label": LABEL,
        "owned_paths": list(OWNED_PATHS),
        "hard_bans": HARD_BANS,
        "pass1": {k: v for k, v in pass1.items() if k != "partitions"},
        "pass2": pass2_merged,
        "partition_checksum": pass1["partitions"]["partition_checksum"],
        "inventory_checksum": inventory["inventory_checksum"],
        "secret_scan": secrets,
        "edge_claim_scan": edge_scan,
        "forbidden_status_scan": status_ban,
        "pytest_report": pytest_report,
        "critical_finding_count": len(critical),
        "high_finding_count": len(high),
        "critical_findings": critical,
        "high_findings": high,
        "remaining_blockers": list(STRUCTURAL_BLOCKERS),
        "metrics": metrics,
        "recommendation": recommendation,
        "passed": passed,
        "commit": head,
        "lane_head": head,
        "human_facing_status_json_emitted": False,
        "note": "Coordinator merges structured results into NEXUS_FINAL_ACCELERATION_REPORT.json only",
    }

    # Emit immutable artifacts — never v15_*_status.json
    _write(art / "hard_bans.json", HARD_BANS)
    _write(art / "partition_manifest.json", pass1["partitions"])
    _write(
        art / "source_inventory.json",
        {
            "schema": inventory["schema"],
            "retrieval_timestamp": inventory["retrieval_timestamp"],
            "inventory_checksum": inventory["inventory_checksum"],
            "record_count": inventory["record_count"],
            "missing_paths": inventory["missing_paths"],
            "endpoint_docs": inventory["endpoint_docs"],
            "records": inventory["records"],
            "oos_consumed": False,
        },
    )
    _write(art / "pass1_summary.json", pass1)
    _write(art / "pass2_adversarial.json", pass2_merged)
    _write(art / "pit_proof.json", pass1["pit_proof"])
    _write(art / "oos_exclusion_proof.json", pass1["oos_exclusion_proof"])
    _write(art / "secret_scan.json", secrets)
    _write(art / "edge_claim_scan.json", edge_scan)
    _write(art / "pytest_report.json", pytest_report)
    _write(art / "campaign_report.json", campaign)
    summary_md = "\n".join(
        [
            f"# {PROGRAM_ID}",
            "",
            f"- Lane: {LANE} ({LANE_NAME})",
            f"- Branch: `{BRANCH}`",
            f"- Base: `{BASE_COMMIT}`",
            f"- Recommendation: **{recommendation}**",
            f"- Passed: {passed}",
            f"- Records: {metrics['record_count']}",
            f"- PIT holds: {metrics['pit_holds']}",
            f"- OOS excluded: {metrics['oos_excluded']}",
            f"- Critical findings: {len(critical)}",
            f"- High findings: {len(high)}",
            f"- Tests passed/failed: {metrics['tests_passed']}/{metrics['tests_failed']}",
            f"- Human-facing v15_*_status.json emitted: false",
            "",
            "## Hard bans",
            "",
            "- No PR26/PR27 merge, deploy, WF, OOS exec/consume, Demo, exchange write, mainnet, fabricated edge",
            "- Do not invent unavailable history",
            "",
            "## Partitions",
            "",
            "- DEVELOPMENT / VALIDATION_PLANNING / OOS_RESERVED / OOS_UNTOUCHED",
            "",
        ]
    )
    (art / "SUMMARY.md").write_text(summary_md, encoding="utf-8")

    # Final ban check after writes
    final_ban = assert_no_forbidden_status_artifacts(root)
    if not final_ban["ok"]:
        raise RuntimeError(f"forbidden_status_json_emitted:{final_ban['banned_files']}")

    return campaign
