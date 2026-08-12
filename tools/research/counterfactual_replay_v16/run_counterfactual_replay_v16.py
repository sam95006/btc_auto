#!/usr/bin/env python3
"""Run V16-B Counterfactual Replay Engine and write immutable artifacts.

HARD BAN: no *_status.json and no status/report markdown.
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
        "tests/counterfactual_replay_v16",
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
    from backend.nexus_counterfactual_replay_v16.harness import run_counterfactual_lab

    head = _git_head()
    pytest_info = _run_pytest()
    result = run_counterfactual_lab(
        root=ROOT,
        write_artifact=True,
        commit=head,
        pytest_info=pytest_info,
    )
    # Machine-readable stdout only — never a status JSON file.
    print(
        json.dumps(
            {
                "lane": result.get("lane"),
                "lane_result": result.get("lane_result"),
                "fingerprint": (result.get("replay") or {}).get("fingerprint"),
                "three_pass": (result.get("three_pass") or {}).get("all_passed"),
                "pytest": pytest_info.get("passed"),
                "tests": pytest_info.get("tests"),
                "wrote_status_json": False,
                "wrote_status_report": False,
                "artifacts": result.get("artifacts_written"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if not pytest_info.get("passed"):
        return 1
    if result.get("lane_result") != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
