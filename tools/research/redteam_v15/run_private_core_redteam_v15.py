#!/usr/bin/env python3
"""Run NEXUS V15-L Private Core Final False-Pass Red Team (two-pass capable)."""
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
    parser = argparse.ArgumentParser(description="V15-L Private Core Final False-Pass Red Team")
    parser.add_argument("--pass", dest="pass_number", type=int, default=1, choices=[1, 2])
    parser.add_argument("--no-artifact", action="store_true")
    args = parser.parse_args()

    from backend.nexus_private_core_redteam.redteam import run_private_core_redteam

    head = _git_head()
    status = run_private_core_redteam(
        write_artifact=not args.no_artifact,
        root=ROOT,
        commit=head,
        pass_number=args.pass_number,
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
                "production_ast": status.get("production_ast"),
                "exchange_write_attempt_count": status.get("exchange_write_attempt_count"),
                "secret_leak_count": status.get("secret_leak_count"),
                "mainnet_client_created_count": status.get("mainnet_client_created_count"),
                "critical_findings": status.get("critical_findings"),
                "v15_readiness_blocked_by_survivors": status.get(
                    "v15_readiness_blocked_by_survivors"
                ),
                "commit": status.get("commit"),
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
    if int(status.get("mainnet_client_created_count") or 0) != 0:
        return 5
    if int((status.get("production_ast") or {}).get("survivors") or 0) != 0:
        return 7
    return 0 if status.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
