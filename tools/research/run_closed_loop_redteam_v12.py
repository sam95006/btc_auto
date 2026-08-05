#!/usr/bin/env python3
"""Run NEXUS V12-F Closed-Loop Red Team and write immutable + runtime artifacts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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


def main() -> int:
    from backend.nexus_autonomy.closed_loop_redteam_v12.redteam import run_closed_loop_redteam

    head = _git_head()
    status = run_closed_loop_redteam(write_artifact=True, write_runtime=True, root=ROOT, commit=head)
    print(
        json.dumps(
            {
                "recommendation": status.get("recommendation"),
                "passed": status.get("passed"),
                "scenario_pass_count": status.get("scenario_pass_count"),
                "scenario_total_count": status.get("scenario_total_count"),
                "attack_blocked_count": status.get("attack_blocked_count"),
                "exchange_write_attempt_count": status.get("exchange_write_attempt_count"),
                "secret_leak_count": status.get("secret_leak_count"),
                "mainnet_client_created_count": status.get("mainnet_client_created_count"),
                "critical_findings": status.get("critical_findings"),
                "commit": status.get("commit"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if int(status.get("exchange_write_attempt_count") or 0) != 0:
        return 3
    if int(status.get("secret_leak_count") or 0) != 0:
        return 4
    if int(status.get("mainnet_client_created_count") or 0) != 0:
        return 5
    return 0 if status.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
