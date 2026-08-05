#!/usr/bin/env python3
"""V13-A Microstructure 14-day Capture Operations runner.

Synthetic preflight + adversarial pass only. Never starts live capture.
Hard bans: no Event Study, no Demo/Shadow/exchange/mainnet, no PR27 merge,
no G deletion, no raw prior campaign modification.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME"))


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def secret_scan(owned_paths: list[Path]) -> dict:
    bad: list[str] = []
    pat = re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY")
    for base in owned_paths:
        if not base.exists():
            continue
        paths = [base] if base.is_file() else list(base.rglob("*"))
        for p in paths:
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".py", ".md", ".json", ".yml", ".yaml", ".toml", ".txt"}:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if pat.search(text):
                bad.append(str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p))
    return {"secret_leak_count": len(bad), "secret_leak_paths": bad}


def write_artifacts(out_dir: Path, both: dict, secret: dict, git_head: str | None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    pass1 = both["pass1"]
    pass2 = both["pass2"]
    design = pass1["campaign_design"]
    preflight = pass1["preflight"]
    scenarios = {
        k: (v.get("status") if isinstance(v, dict) else v)
        for k, v in (preflight.get("scenarios") or {}).items()
    }

    status = {
        "schema": "v13_a_microstructure_14d_operations_status",
        "lane": "V13-A",
        "V13_A_Microstructure_14d_Operations_status": "PASS"
        if both.get("all_passed") and secret.get("secret_leak_count") == 0
        else "FAIL",
        "created_at": _utc(),
        "branch": "feature/v13-microstructure-14d-operations",
        "base_head": "abd2195ef6d79f609dd261b5e9c5402599625a64",
        "git_head": git_head,
        "campaign_id": design["campaign_id"],
        "target_calendar_days": design["target_calendar_days"],
        "symbol_count": design["symbol_count"],
        "families": design["families"],
        "storage_floor_gib": design["storage"]["floor_free_disk_gib"],
        "hard_cap_gib": design["storage"]["hard_cap_gib"],
        "durability": design["durability"],
        "pass1_all_passed": pass1.get("all_passed"),
        "pass2_all_passed": pass2.get("all_passed"),
        "preflight_scenarios": scenarios,
        "adversarial_negative_tests": [
            {"name": t["name"], "status": t["status"]} for t in pass2.get("negative_tests") or []
        ],
        "capture_start_gates_decision": (pass1.get("capture_start_gates") or {}).get("decision"),
        "live_capture_started": False,
        "event_study_readiness_status": "NOT_READY",
        "event_study_real_execution": False,
        "exchange_write_attempt_count": 0,
        "demo_used": False,
        "mainnet_used": False,
        "shadow_used": False,
        "PR27_merged": False,
        "G_deleted": False,
        "raw_prior_campaign_modified": False,
        "auto_integration": False,
        "secret_leak_count": secret.get("secret_leak_count"),
        "owned_paths_only": True,
        "coordinator_only_live_launch": True,
        "blockers": _collect_blockers(both, secret),
    }

    readiness = {
        "schema": "event_study_readiness_v1",
        "event_study_readiness_status": "NOT_READY",
        "event_study_real_execution": False,
        "note": "V13-A must not start Event Study; readiness remains NOT_READY.",
        "created_at": _utc(),
    }

    payloads = {
        "operations_status.json": status,
        "campaign_design.json": design,
        "pass1_evidence.json": pass1,
        "pass2_adversarial.json": pass2,
        "preflight_scenarios.json": preflight,
        "capture_start_gates.json": pass1.get("capture_start_gates"),
        "storage_budget.json": pass1.get("storage_budget"),
        "open_tail_seal_policy.json": pass1.get("open_tail_seal_policy"),
        "retained_classifications.json": pass1.get("retained_classifications"),
        "event_study_readiness.json": readiness,
        "secret_scan.json": secret,
        "both_passes.json": both,
        "README.md": (
            "# V13-A Microstructure 14-day Capture Operations\n\n"
            "Campaign design: `ms_accum_v13_integrity_14d`.\n"
            "Synthetic preflight + adversarial negative tests only.\n"
            "`live_capture_started=false` — Coordinator alone may launch real collector.\n"
            "Event Study remains NOT_READY. Prior raw campaign unmodified.\n"
        ),
    }
    for name, body in payloads.items():
        path = out_dir / name
        if isinstance(body, str):
            path.write_text(body, encoding="utf-8")
        else:
            path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return status


def _collect_blockers(both: dict, secret: dict) -> list[str]:
    blockers: list[str] = []
    if not both.get("all_passed"):
        if not (both.get("pass1") or {}).get("all_passed"):
            blockers.append("pass1_preflight_incomplete")
            scenarios = ((both.get("pass1") or {}).get("preflight") or {}).get("scenarios") or {}
            for name, sc in scenarios.items():
                if isinstance(sc, dict) and sc.get("status") != "PASS":
                    blockers.append(f"preflight:{name}")
        if not (both.get("pass2") or {}).get("all_passed"):
            blockers.append("pass2_adversarial_incomplete")
            for t in (both.get("pass2") or {}).get("negative_tests") or []:
                if t.get("status") != "PASS":
                    blockers.append(f"neg:{t.get('name')}")
    if secret.get("secret_leak_count"):
        blockers.append("secret_leak")
    # Always surface operational blockers for live (expected).
    blockers.append("live_capture_not_started_coordinator_only")
    blockers.append("event_study_NOT_READY")
    blockers.append("14d_live_data_not_yet_accumulated")
    return blockers


def main(argv: list[str] | None = None) -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    os.environ["DEMO"] = "false"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir",
        default=str(ROOT / "artifacts/readiness/immutable/v13_a_microstructure_14d_operations"),
    )
    parser.add_argument("--disk-root", default="D:\\")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from backend.nexus_microstructure.ops_v13.controller import (
        MicrostructureOperationsControllerV13,
    )

    work = ROOT / "artifacts" / "readiness" / "tmp" / "v13_a_microstructure_14d_work"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)

    ctl = MicrostructureOperationsControllerV13(
        ROOT,
        work_root=work,
        disk_root=args.disk_root,
        previous_campaign_finalized=True,
    )
    both = ctl.run_both_passes()

    owned = [
        ROOT / "backend/nexus_microstructure/ops_v13",
        ROOT / "tools/research/run_microstructure_operations_v13.py",
        ROOT / "tests/test_microstructure_operations_v13.py",
        ROOT / "tests/test_microstructure_operations_v13_adversarial.py",
        Path(args.artifact_dir),
    ]
    secret = secret_scan(owned)

    git_head = None
    try:
        import subprocess

        git_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
    except Exception:  # noqa: BLE001
        git_head = None

    status = write_artifacts(Path(args.artifact_dir), both, secret, git_head)

    # Runtime status for founder matrix — live_capture_started must remain false.
    runtime_status = {
        **status,
        "worktree": str(ROOT),
        "runtime_status_path": str(RUNTIME / "v13_a_microstructure_14d_status.json"),
        "artifact_dir": str(args.artifact_dir),
        "lane": "V13-A",
        "live_capture_started": False,
        "auto_integration": False,
    }
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "v13_a_microstructure_14d_status.json").write_text(
        json.dumps(runtime_status, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "V13_A_Microstructure_14d_Operations_status": status[
            "V13_A_Microstructure_14d_Operations_status"
        ],
        "campaign_id": status["campaign_id"],
        "live_capture_started": False,
        "event_study_readiness_status": "NOT_READY",
        "pass1_all_passed": status["pass1_all_passed"],
        "pass2_all_passed": status["pass2_all_passed"],
        "blockers": status["blockers"],
        "artifact_dir": str(args.artifact_dir),
        "runtime_status": str(RUNTIME / "v13_a_microstructure_14d_status.json"),
        "auto_integration": False,
    }
    print(json.dumps(summary, indent=2), flush=True)
    ok = (
        status["V13_A_Microstructure_14d_Operations_status"] == "PASS"
        and status["live_capture_started"] is False
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
