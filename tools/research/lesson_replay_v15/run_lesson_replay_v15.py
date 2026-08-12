#!/usr/bin/env python3
"""Run V15-I Reflection and Lesson Replay Lab and write immutable artifacts.

HARD BAN: no *_status.json.
"""
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
        "tests/lesson_replay_v15",
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
    tests = 0
    for line in (proc.stdout or "").splitlines()[::-1]:
        if " passed" in line:
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
    from backend.nexus_lesson_replay_v15.harness import run_lesson_replay_lab

    head = _git_head()
    pytest_info = _run_pytest()
    result = run_lesson_replay_lab(
        root=ROOT,
        write_artifact=True,
        commit=head,
        pytest_info=pytest_info,
    )
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "pass": result.get("pass"),
                "REAL_LESSON_PREVENTION_STATUS": result.get("REAL_LESSON_PREVENTION_STATUS"),
                "replay_lab_status": result.get("replay_lab_status"),
                "V2_3_complete": result.get("V2_3_complete"),
                "new_policy_effect_lesson_count": result.get("new_policy_effect_lesson_count"),
                "secret_leak_count": result.get("secret_leak_count"),
                "wrote_status_json": result.get("wrote_status_json"),
                "digest": result.get("digest"),
                "head_commit": result.get("head_commit"),
                "pytest_passed": pytest_info.get("passed"),
                "auto_integrate": False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if not pytest_info.get("passed"):
        return 2
    if int(result.get("secret_leak_count") or 0) != 0:
        return 4
    if int(result.get("exchange_write_attempt_count") or 0) != 0:
        return 3
    if result.get("wrote_status_json"):
        return 5
    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
