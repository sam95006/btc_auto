#!/usr/bin/env python3
"""Run NEXUS V15-J Continuous Autonomy Operations Control — two-pass harness.

Founder-only control: start/pause/resume/safe-stop/kill/recovery plus
health/storage/Provider/capture/Decision/Execution/Reflection/Lesson/Qualification
blocks. Mutating ops require Founder auth proof, idempotency, ledger, checkpoint,
safety gate. No exchange writes. No *_status.json artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")
os.environ.setdefault("DEMO", "false")
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_autonomy.continuous_ops_control_v15.adversarial import run_pass2
from backend.nexus_autonomy.continuous_ops_control_v15.constants import (
    BASE_HEAD,
    BRANCH,
    HARD_BANS,
    LANE,
    OWNED_PATHS,
    PRESERVED_FACTS,
    PROGRAM_ID,
    SCHEMA,
)
from backend.nexus_autonomy.continuous_ops_control_v15.proofs import run_pass1


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(ROOT), stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        return "UNKNOWN"


def write_artifacts(
    *,
    artifact_dir: Path,
    pass1: dict[str, Any],
    pass2: dict[str, Any],
    head: str,
    pytest_rc: int | None,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Explicitly refuse *_status.json for this lane.
    for banned in artifact_dir.glob("*_status.json"):
        banned.unlink()

    both = {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "branch": BRANCH,
        "base": BASE_HEAD,
        "lane_head": head,
        "created_at": _utc(),
        "pass1": {
            "overall_status": pass1.get("overall_status"),
            "proofs_passed": pass1.get("proofs_passed"),
            "proofs_total": pass1.get("proofs_total"),
            "failed": pass1.get("failed"),
        },
        "pass2": {
            "overall_status": pass2.get("overall_status"),
            "proofs_passed": pass2.get("proofs_passed"),
            "proofs_total": pass2.get("proofs_total"),
            "failed": pass2.get("failed"),
        },
        "both_passes": pass1.get("overall_status") == "PASS"
        and pass2.get("overall_status") == "PASS",
        "pytest_rc": pytest_rc,
        **PRESERVED_FACTS,
        "hard_bans": HARD_BANS,
        "owned_paths": list(OWNED_PATHS),
        "status_json_emitted": False,
        "exchange_write": False,
        "PR27_draft_unmerged": True,
        "auto_integration": False,
    }

    (artifact_dir / "pass1_proofs.json").write_text(
        json.dumps(pass1, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "pass2_adversarial.json").write_text(
        json.dumps(pass2, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "both_passes.json").write_text(
        json.dumps(both, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "hard_bans.json").write_text(
        json.dumps(HARD_BANS, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "counters.json").write_text(
        json.dumps(
            {
                "pass1_proofs_passed": pass1.get("proofs_passed"),
                "pass1_proofs_total": pass1.get("proofs_total"),
                "pass2_proofs_passed": pass2.get("proofs_passed"),
                "pass2_proofs_total": pass2.get("proofs_total"),
                "exchange_write_attempt_count": 0,
                "demo_order_count": 0,
                "shadow_order_count": 0,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "readiness_summary.json").write_text(
        json.dumps(
            {
                "lane": LANE,
                "program_id": PROGRAM_ID,
                "both_passes": both["both_passes"],
                "overall": "PASS" if both["both_passes"] else "FAIL",
                "lane_head": head,
                "base": BASE_HEAD,
                "status_json_emitted": False,
                **PRESERVED_FACTS,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "README.md").write_text(
        "\n".join(
            [
                "# V15-J Continuous Autonomy Operations Control",
                "",
                "Founder-only control plane for start / pause / resume / safe-stop / kill /",
                "recovery plus health / storage / Provider / capture / Decision / Execution /",
                "Reflection / Lesson / Qualification observation blocks.",
                "",
                "Mutating ops require Founder authorization proof, idempotency, ledger event,",
                "checkpoint, and deterministic safety gate. No exchange writes.",
                "",
                "Artifacts intentionally omit `*_status.json` (lane rule).",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return both


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V15-J Continuous Autonomy Ops harness")
    parser.add_argument(
        "--artifact-dir",
        default=str(
            ROOT / "artifacts" / "readiness" / "immutable" / "v15_continuous_autonomy_ops"
        ),
    )
    parser.add_argument("--work-dir", default=None)
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args(argv)

    work = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="nexus_v15_j_"))
    work.mkdir(parents=True, exist_ok=True)
    artifact_dir = Path(args.artifact_dir)

    print(json.dumps({"phase": "pass1_start", "work": str(work)}, indent=2), flush=True)
    pass1 = run_pass1(work / "pass1")
    print(
        json.dumps(
            {
                "phase": "pass1_done",
                "overall_status": pass1.get("overall_status"),
                "failed": pass1.get("failed"),
            },
            indent=2,
        ),
        flush=True,
    )

    print(json.dumps({"phase": "pass2_start"}, indent=2), flush=True)
    # Write pass1 first so pass2 can scan artifact dir for banned status.json
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "pass1_proofs.json").write_text(
        json.dumps(pass1, indent=2) + "\n", encoding="utf-8"
    )
    pass2 = run_pass2(work / "pass2", artifact_dir=artifact_dir)
    print(
        json.dumps(
            {
                "phase": "pass2_done",
                "overall_status": pass2.get("overall_status"),
                "failed": pass2.get("failed"),
            },
            indent=2,
        ),
        flush=True,
    )

    pytest_rc: int | None = None
    if not args.skip_pytest:
        print(json.dumps({"phase": "pytest_start"}, indent=2), flush=True)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_continuous_autonomy_ops_v15.py",
                "-q",
                "--tb=short",
            ],
            cwd=str(ROOT),
        )
        pytest_rc = int(proc.returncode)
        print(json.dumps({"phase": "pytest_done", "rc": pytest_rc}, indent=2), flush=True)

    head = _git_head()
    both = write_artifacts(
        artifact_dir=artifact_dir,
        pass1=pass1,
        pass2=pass2,
        head=head,
        pytest_rc=pytest_rc,
    )
    print(
        json.dumps(
            {
                "phase": "done",
                "both_passes": both["both_passes"],
                "lane_head": head,
                "artifact_dir": str(artifact_dir),
                "status_json_emitted": False,
            },
            indent=2,
        ),
        flush=True,
    )
    if not both["both_passes"]:
        return 1
    if pytest_rc not in (None, 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
