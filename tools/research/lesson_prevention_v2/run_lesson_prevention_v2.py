#!/usr/bin/env python3
"""Run V14-G Lesson Prevention Proof V2 and write immutable + runtime artifacts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)


def _git_head() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _run_pytest() -> dict:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/lesson_prevention_v2",
        "-q",
        "--tb=line",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    passed = proc.returncode == 0
    # Count passed tests from summary line if present
    tests = 0
    for line in (proc.stdout or "").splitlines()[::-1]:
        if " passed" in line:
            # e.g. "12 passed in 0.5s"
            try:
                tests = int(line.strip().split()[0])
            except Exception:  # noqa: BLE001
                tests = 0
            break
    return {
        "exit_code": proc.returncode,
        "passed": passed,
        "tests": tests,
        "stdout_tail": "\n".join((proc.stdout or "").splitlines()[-20:]),
        "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-10:]),
    }


def main() -> int:
    from backend.nexus_lesson_prevention_v2.harness import run_lesson_prevention_v2

    head = _git_head()
    pytest_info = _run_pytest()
    status = run_lesson_prevention_v2(
        root=ROOT,
        write_artifact=True,
        write_runtime=True,
        commit=head,
        pytest_info=pytest_info,
        pushed=False,
    )
    print(
        json.dumps(
            {
                "status": status.get("status"),
                "pass": status.get("pass"),
                "REAL_LESSON_PREVENTION_STATUS": status.get("REAL_LESSON_PREVENTION_STATUS"),
                "mechanics_proof_status": status.get("mechanics_proof_status"),
                "V2_3_complete": status.get("V2_3_complete"),
                "new_policy_effect_lesson_count": status.get("new_policy_effect_lesson_count"),
                "secret_leak_count": status.get("secret_leak_count"),
                "digest": status.get("digest"),
                "head_commit": status.get("head_commit"),
                "pytest_passed": pytest_info.get("passed"),
                "auto_integrate": False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if not pytest_info.get("passed"):
        return 2
    if int(status.get("secret_leak_count") or 0) != 0:
        return 4
    if int(status.get("exchange_write_attempt_count") or 0) != 0:
        return 3
    return 0 if status.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
