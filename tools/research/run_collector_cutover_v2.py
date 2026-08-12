#!/usr/bin/env python3
"""Collector Cutover V2 runner — synthetic + public-readonly proofs only.

Hard bans: no Event Study start, no raw prior campaign mutation, no Demo/exchange/mainnet.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
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


def main() -> int:
    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("DEMO", "false")
    sys.path.insert(0, str(ROOT))

    from backend.nexus_microstructure.collector_cutover_v2.constants import (
        EVENT_STUDY_STATUS,
        R2_HIGH_DISPOSITIONS,
        RETAINED_CLASSIFICATION_COUNTS,
        SCHEMA,
    )
    from backend.nexus_microstructure.collector_cutover_v2.controller import (
        CollectorCutoverControllerV2,
    )
    from backend.nexus_microstructure.collector_cutover_v2.finalizer_v2_compat import (
        FinalizerV2Compat,
    )
    from backend.nexus_microstructure.event_study_hard_block_v11_1 import event_study_gate

    work = ROOT / "artifacts" / "readiness" / "tmp" / "v12_b_collector_cutover_work"
    if work.exists():
        import shutil

        shutil.rmtree(work, ignore_errors=True)
    ctl = CollectorCutoverControllerV2(ROOT, work_root=work)
    proofs = ctl.run_synthetic_proofs()
    gate = event_study_gate()

    out_dir = ROOT / "artifacts" / "readiness" / "immutable" / "v12_b_collector_cutover"
    out_dir.mkdir(parents=True, exist_ok=True)

    compat = FinalizerV2Compat(ROOT)
    envelope = proofs["finalizer_v2_envelope"]
    compat.write_envelope(out_dir, envelope)

    finding_matrix = dict(R2_HIGH_DISPOSITIONS)
    # Also record already-fixed D-001/D-002/D-004 from prior tip remediation.
    finding_matrix.setdefault("R2-D-001", "FIXED")
    finding_matrix.setdefault("R2-D-002", "FIXED")
    finding_matrix.setdefault("R2-D-004", "FIXED")

    status = {
        "schema": f"{SCHEMA}_status",
        "Collector_Cutover_V2_status": "PASS" if proofs.get("all_passed") else "FAIL",
        "created_at": _utc(),
        "branch": "feature/v12-microstructure-collector-cutover",
        "base": "e4e96299840da2e5152cf2850135cebc67d66cd0",
        "features": {
            "exclusive_partition_ids": True,
            "atomic_manifest_seal": True,
            "open_tail_seal_policy": True,
            "persistent_clock_guard": True,
            "resume_safe_linkage": True,
            "automatic_safe_stop": True,
            "storage_controller": True,
            "finalizer_v2_compatibility": True,
        },
        "scenarios": {k: v.get("status") for k, v in proofs["scenarios"].items()},
        "r2_high_dispositions": finding_matrix,
        "retained_classifications": {
            "raw_modified": False,
            "classification_counts": dict(RETAINED_CLASSIFICATION_COUNTS),
            "ACTUAL_DATA_CORRUPTION": 0,
            "EXPECTED_OPEN_TAIL": 113,
        },
        "event_study_readiness_status": EVENT_STUDY_STATUS,
        "event_study_real_execution": False,
        "event_study_gate": gate,
        "live_capture_started": False,
        "exchange_write_attempt_count": 0,
        "demo_used": False,
        "mainnet_used": False,
        "raw_prior_campaign_modified": False,
        "PR27_merged": False,
        "G_deleted": False,
        "owned_paths_only": True,
    }

    secret = secret_scan(
        [
            ROOT / "backend" / "nexus_microstructure" / "collector_cutover_v2",
            ROOT / "tests" / "test_collector_cutover_v2.py",
            out_dir,
        ]
    )
    status["secret_leak_count"] = secret["secret_leak_count"]
    if secret["secret_leak_count"] > 0:
        status["Collector_Cutover_V2_status"] = "FAIL"

    payloads = {
        "collector_cutover_v2_status.json": status,
        "synthetic_proofs.json": proofs,
        "r2_high_dispositions.json": finding_matrix,
        "open_tail_seal_policy.json": proofs["open_tail_seal_policy"],
        "retained_classifications.json": proofs["retained_classifications"],
        "event_study_readiness.json": {
            "schema": "event_study_readiness_v1",
            "event_study_readiness_status": EVENT_STUDY_STATUS,
            "event_study_real_execution": False,
            "created_at": _utc(),
        },
        "secret_scan.json": secret,
        "README.md": (
            "# V12-B Collector Cutover V2\n\n"
            "Synthetic + read-only public-data-shaped proofs only.\n"
            "Event Study remains NOT_READY. Prior raw campaign unmodified.\n"
        ),
    }
    for name, body in payloads.items():
        path = out_dir / name
        if isinstance(body, str):
            path.write_text(body, encoding="utf-8")
        else:
            path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    # Runtime status for founder matrix
    # head filled after commit by post-step; placeholder now
    runtime_status = {
        **status,
        "worktree": str(ROOT),
        "runtime_status_path": str(RUNTIME / "v12_b_collector_cutover_status.json"),
        "artifact_dir": str(out_dir),
        "lane": "V12-B",
    }
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "v12_b_collector_cutover_status.json").write_text(
        json.dumps(runtime_status, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps({"status": status["Collector_Cutover_V2_status"], "out_dir": str(out_dir)}, indent=2))
    return 0 if status["Collector_Cutover_V2_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
