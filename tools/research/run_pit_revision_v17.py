"""Run Founder V17-D point-in-time / revision control lab and emit evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.nexus_pit_revision_v17.constants import (  # noqa: E402
    BASE_COMMIT,
    BRANCH,
    EVIDENCE_PATH,
    LANE,
    LANE_NAME,
    SCHEMA,
)
from backend.nexus_pit_revision_v17.harness import run_pit_revision_lab  # noqa: E402
from backend.nexus_pit_revision_v17.redteam import run_future_leakage_redteam  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head(repo: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _atomic_write_json(path: Path, obj: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    data = payload.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return digest


def build_evidence(
    *,
    lab: dict[str, Any],
    pytest_passed: int,
    pytest_failed: int,
    head: str,
) -> dict[str, Any]:
    redteam = lab["redteam"]
    summary = lab["summary"]
    status = "PASS" if lab["status"] == "PASS" and redteam["survivor_count"] == 0 and pytest_failed == 0 else "FAIL"
    return {
        "schema": "v17_d_pit_revision_evidence_v1",
        "generated_at": _utc(),
        "status": status,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base": BASE_COMMIT,
        "HEAD": head,
        "worktree": str(REPO_ROOT),
        "module_schema": SCHEMA,
        "time_axes": summary.get("time_axes"),
        "capabilities": summary.get("capabilities"),
        "leakage_survivors": redteam["survivor_count"],
        "leakage_survivor_ids": redteam["survivors"],
        "future_leakage_redteam": {
            "attack_count": redteam["attack_count"],
            "blocked_count": redteam["blocked_count"],
            "survivor_count": redteam["survivor_count"],
            "pass": redteam["pass"],
        },
        "tests": {
            "suite": "tests/pit_revision_v17/",
            "passed": pytest_passed,
            "failed": pytest_failed,
        },
        "artifacts": lab.get("artifacts"),
        "formal_wf_executed": False,
        "oos_claimed": False,
        "exchange_write_attempt_count": 0,
        "mainnet_client_count": 0,
        "report_edited": False,
        "fixture_only": True,
        "real_market_data": False,
        "non_claims": summary.get("non_claims"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V17-D PIT revision lab")
    parser.add_argument(
        "--evidence",
        default=EVIDENCE_PATH,
        help="Evidence JSON output path",
    )
    parser.add_argument(
        "--skip-pytest",
        action="store_true",
        help="Skip invoking pytest (use counts from --pytest-passed/failed)",
    )
    parser.add_argument("--pytest-passed", type=int, default=0)
    parser.add_argument("--pytest-failed", type=int, default=0)
    args = parser.parse_args()

    lab = run_pit_revision_lab(repo_root=REPO_ROOT)
    head = _git_head(REPO_ROOT)

    pytest_passed = args.pytest_passed
    pytest_failed = args.pytest_failed
    if not args.skip_pytest:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/pit_revision_v17/",
                "-q",
                "--tb=no",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        # Parse "N passed" from pytest -q summary line.
        out = (proc.stdout or "") + (proc.stderr or "")
        pytest_failed = 0 if proc.returncode == 0 else 1
        pytest_passed = 0
        for token in out.replace(",", " ").split():
            if token.isdigit():
                # last integer before 'passed' wins when scanning with context
                pass
        import re

        m = re.search(r"(\d+)\s+passed", out)
        if m:
            pytest_passed = int(m.group(1))
        m_fail = re.search(r"(\d+)\s+failed", out)
        if m_fail:
            pytest_failed = int(m_fail.group(1))
        elif proc.returncode != 0 and pytest_passed == 0:
            pytest_failed = max(pytest_failed, 1)

    evidence = build_evidence(
        lab=lab,
        pytest_passed=pytest_passed,
        pytest_failed=pytest_failed,
        head=head,
    )
    digest = _atomic_write_json(Path(args.evidence), evidence)
    evidence_with_hash = dict(evidence)
    evidence_with_hash["evidence_sha256"] = digest
    _atomic_write_json(Path(args.evidence), evidence_with_hash)

    print(
        json.dumps(
            {
                "status": evidence_with_hash["status"],
                "HEAD": head,
                "leakage_survivors": evidence_with_hash["leakage_survivors"],
                "tests": evidence_with_hash["tests"],
                "evidence": args.evidence,
                "evidence_sha256": digest,
            },
            indent=2,
        )
    )
    return 0 if evidence_with_hash["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
