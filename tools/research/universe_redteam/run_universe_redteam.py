#!/usr/bin/env python3
"""Run NEXUS V14-I Universe Lineage Red Team (two-pass capable)."""
from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description="V14-I Universe Lineage Red Team")
    parser.add_argument("--pass", dest="pass_number", type=int, default=2, choices=[1, 2])
    parser.add_argument("--no-runtime", action="store_true")
    parser.add_argument("--no-artifact", action="store_true")
    parser.add_argument(
        "--runtime-path",
        default=r"D:\NEXUS_RUNTIME\v14_i_status.json",
        help="Runtime lane status JSON path",
    )
    args = parser.parse_args()

    from backend.nexus_universe_redteam.redteam import run_universe_redteam

    head = _git_head()
    status = run_universe_redteam(
        write_artifact=not args.no_artifact,
        write_runtime=not args.no_runtime,
        root=ROOT,
        commit=head,
        pass_number=args.pass_number,
        runtime_path=args.runtime_path,
    )
    print(
        json.dumps(
            {
                "recommendation": status.get("recommendation"),
                "passed": status.get("passed"),
                "pass_number": status.get("pass_number"),
                "scenario_pass_count": status.get("scenario_pass_count"),
                "scenario_total_count": status.get("scenario_total_count"),
                "fixture_pass_count": status.get("fixture_pass_count"),
                "fixture_total_count": status.get("fixture_total_count"),
                "attack_blocked_count": status.get("attack_blocked_count"),
                "platform_blocked_count": status.get("platform_blocked_count"),
                "platform_blocked_pass_count": status.get("platform_blocked_pass_count"),
                "exchange_write_attempt_count": status.get("exchange_write_attempt_count"),
                "secret_leak_count": status.get("secret_leak_count"),
                "mainnet_client_created_count": status.get("mainnet_client_created_count"),
                "critical_findings": status.get("critical_findings"),
                "high_findings": status.get("high_findings"),
                "remaining_blockers": status.get("remaining_blockers"),
                "commit": status.get("commit"),
                "auto_integration": status.get("auto_integration"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if int(status.get("platform_blocked_pass_count") or 0) != 0:
        return 6
    if int(status.get("exchange_write_attempt_count") or 0) != 0:
        return 3
    if int(status.get("secret_leak_count") or 0) != 0:
        return 4
    if not status.get("passed"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
