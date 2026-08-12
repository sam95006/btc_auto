#!/usr/bin/env python3
"""Microstructure Operations V10 runner — dry-run / controller scaffolding by default.

Hard bans: no Event Study start, no strategy generation, no exchange write.
Does not start a live capture unless all gates PASS and --enable-live-capture is set;
even then this runner only authorizes — it does not invoke the collector.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
                bad.append(str(p.relative_to(ROOT)))
    return {"secret_leak_count": len(bad), "secret_leak_paths": bad}


def write_artifacts(out_dir: Path, cycle: dict, secret: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    readiness = {
        "schema": "event_study_readiness_v1",
        "event_study_readiness_status": "NOT_READY",
        "event_study_real_execution": False,
        "note": "Ops V10 must not start Event Study; readiness remains NOT_READY.",
        "created_at": _utc(),
    }
    status = {
        "schema": "v10_microstructure_operations_status",
        "Microstructure_Operations_V10_status": "PASS"
        if cycle.get("live_capture_started") is False
        and cycle.get("event_study_readiness_status") == "NOT_READY"
        and secret.get("secret_leak_count") == 0
        else "FAIL",
        "created_at": _utc(),
        "live_capture_started": cycle.get("live_capture_started"),
        "segment_plan": cycle.get("segment_plan"),
        "capture_start_gates_decision": (cycle.get("capture_start_gates") or {}).get("decision"),
        "all_hard_gates_passed": (cycle.get("capture_start_gates") or {}).get("all_hard_gates_passed"),
        "previous_campaign_id": cycle.get("previous_campaign_id"),
        "previous_campaign_finalized": (cycle.get("finalizer_integration") or {}).get(
            "previous_campaign_finalized"
        ),
        "storage_budget_mode": (cycle.get("storage_budget") or {}).get("mode"),
        "minimum_free_disk_status": (
            (cycle.get("storage_budget") or {}).get("minimum_free_disk") or {}
        ).get("status"),
        "integrity_overall": (cycle.get("integrity_score") or {}).get("integrity_overall"),
        "integrity_score": (cycle.get("integrity_score") or {}).get("integrity_score"),
        "retention_dry_run": True,
        "deletion_executed": False,
        "event_study_readiness_status": "NOT_READY",
        "event_study_real_execution": False,
        "new_strategy_generated_count": 0,
        "exchange_write_attempt_count": 0,
        "profitability_claim_count": 0,
        "secret_leak_count": secret.get("secret_leak_count"),
        "owned_paths_only": True,
    }
    payloads = {
        "operations_status.json": status,
        "capture_start_gates.json": cycle.get("capture_start_gates"),
        "storage_budget.json": cycle.get("storage_budget"),
        "campaign_registry_snapshot.json": cycle.get("campaign_registry"),
        "retention_dry_run.json": cycle.get("retention_dry_run"),
        "integrity_score.json": cycle.get("integrity_score"),
        "automatic_safe_stop.json": cycle.get("automatic_safe_stop"),
        "bounded_resume.json": cycle.get("bounded_resume"),
        "finalizer_integration.json": cycle.get("finalizer_integration"),
        "scheduler_cycle.json": cycle,
        "event_study_readiness.json": readiness,
        "secret_scan.json": secret,
    }
    for name, payload in payloads.items():
        (out_dir / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enable-live-capture",
        action="store_true",
        help="Authorize live capture only if all hard gates PASS (still does not invoke collector).",
    )
    parser.add_argument(
        "--proposed-campaign-id",
        default="ms_accum_v10_bounded_next",
    )
    parser.add_argument(
        "--disk-root",
        default="D:\\",
    )
    parser.add_argument(
        "--artifact-dir",
        default=str(ROOT / "artifacts/readiness/immutable/v10_microstructure_operations"),
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from backend.nexus_microstructure.campaign_scheduler_v10 import CampaignSchedulerV10

    scheduler = CampaignSchedulerV10(ROOT, disk_root=args.disk_root)
    cycle = scheduler.run_controller_cycle(
        proposed_campaign_id=args.proposed_campaign_id,
        enable_live_capture=bool(args.enable_live_capture),
    )

    owned = [
        ROOT / "backend/nexus_microstructure/ops_v10",
        ROOT / "backend/nexus_microstructure/campaign_scheduler_v10.py",
        ROOT / "backend/nexus_microstructure/storage_budget_v10.py",
        ROOT / "tools/research/run_microstructure_operations_v10.py",
        ROOT / "tests/test_microstructure_operations_v10.py",
        ROOT / "artifacts/readiness/immutable/v10_microstructure_operations",
    ]
    secret = secret_scan(owned)
    out_dir = Path(args.artifact_dir)
    write_artifacts(out_dir, cycle, secret)

    summary = {
        "Microstructure_Operations_V10_status": json.loads(
            (out_dir / "operations_status.json").read_text(encoding="utf-8")
        )["Microstructure_Operations_V10_status"],
        "capture_start_gates_decision": cycle["capture_start_gates"]["decision"],
        "live_capture_started": cycle["live_capture_started"],
        "event_study_readiness_status": "NOT_READY",
        "secret_leak_count": secret["secret_leak_count"],
        "artifact_dir": str(out_dir),
    }
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if secret["secret_leak_count"] == 0 and not cycle["live_capture_started"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
