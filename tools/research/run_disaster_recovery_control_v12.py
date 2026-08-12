#!/usr/bin/env python3
"""Run NEXUS V12-D Disaster Recovery Control proof harness.

Hard bans: no Demo / exchange write / mainnet; no PR27 merge; no silent recovery guesses.
Proves: cold/warm restart, LKG/checkpoint restore, ledger-tail reconciliation,
ambiguous blocking, kill switch after recovery, storage migration recovery.
Builds on V11.1 durability invariants.
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

from backend.nexus_recovery.dr_control_v12.constants import (
    BRANCH,
    HARD_BANS,
    LANE,
    PRESERVED_FACTS,
    PROGRAM_ID,
    SCHEMA,
)
from backend.nexus_recovery.dr_control_v12.proofs import run_proof_matrix


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


def build_status(matrix: dict[str, Any], *, head: str) -> dict[str, Any]:
    counters = dict(matrix.get("counters") or {})
    return {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "branch": BRANCH,
        "base": "e4e96299840da2e5152cf2850135cebc67d66cd0",
        "head": head,
        "created_at": _utc(),
        "overall_status": matrix.get("overall_status"),
        "blockers": list(matrix.get("blockers") or []),
        "counters": counters,
        "proofs": matrix.get("proofs"),
        "v11_1_invariants": matrix.get("v11_1_invariants"),
        "hard_bans": HARD_BANS,
        "preserved_facts": PRESERVED_FACTS,
        "owned_paths": [
            "backend/nexus_recovery/dr_control_v12/",
            "tools/research/run_disaster_recovery_control_v12.py",
            "tests/test_disaster_recovery_control_v12.py",
            "artifacts/readiness/immutable/v12_disaster_recovery_control/",
        ],
        "prohibited": [
            "Demo",
            "exchange_write",
            "mainnet",
            "PR27_merge",
            "silent_recovery_guess",
        ],
        "execution_mode": "SIMULATED_FAIL_CLOSED_NO_EXCHANGE_WRITE",
        "PR27_draft_unmerged": True,
        "auto_integration": False,
    }


def write_artifacts(status: dict[str, Any], artifact_dir: Path, runtime_status: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "v12_disaster_recovery_control_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "proof_matrix.json").write_text(
        json.dumps(
            {
                "proofs": status.get("proofs"),
                "v11_1_invariants": status.get("v11_1_invariants"),
                "counters": status.get("counters"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "blockers.json").write_text(
        json.dumps(
            {
                "blockers": status.get("blockers") or [],
                "overall_status": status.get("overall_status"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "counters.json").write_text(
        json.dumps(status.get("counters") or {}, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "README.md").write_text(
        "\n".join(
            [
                "# V12-D Disaster Recovery Control",
                "",
                "Proves cold/warm restart, LKG/checkpoint restore, ledger-tail reconciliation,",
                "ambiguous-state blocking, kill switch after recovery, and storage migration recovery.",
                "",
                "Hard bans: no Demo / exchange write / mainnet; no PR27 merge; no silent recovery guesses.",
                "Builds on V11.1 durability: false LKG banned, checksummed ledger position, owner-only duplicate intent.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runtime_status.parent.mkdir(parents=True, exist_ok=True)
    runtime_status.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V12-D Disaster Recovery Control harness")
    parser.add_argument(
        "--artifact-dir",
        default=str(
            ROOT / "artifacts" / "readiness" / "immutable" / "v12_disaster_recovery_control"
        ),
    )
    parser.add_argument(
        "--runtime-status",
        default=str(Path("D:/NEXUS_RUNTIME/v12_d_disaster_recovery_status.json")),
    )
    parser.add_argument("--work-dir", default=None)
    args = parser.parse_args(argv)

    work = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="nexus_v12_d_"))
    work.mkdir(parents=True, exist_ok=True)

    print(json.dumps({"phase": "start", "work": str(work)}, indent=2), flush=True)
    matrix = run_proof_matrix(work / "matrix")
    head = _git_head()
    status = build_status(matrix, head=head)
    write_artifacts(status, Path(args.artifact_dir), Path(args.runtime_status))
    print(
        json.dumps(
            {
                "phase": "done",
                "overall_status": status["overall_status"],
                "blockers": status["blockers"],
                "counters": status["counters"],
                "head": head,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if not status["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
