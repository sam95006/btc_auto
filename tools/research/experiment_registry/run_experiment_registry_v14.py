#!/usr/bin/env python3
"""V14-J Experiment Registry campaign harness (two-pass capable).

Emits artifacts under:
  artifacts/readiness/immutable/v14_experiment_registry/

Writes D:\\NEXUS_RUNTIME\\v14_j_status.json by default.

Hard bans: no OOS consumption, no Demo/exchange, no PR27 merge,
no silent favorable-run cherry-picking, no auto-integration.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)


def main() -> int:
    parser = argparse.ArgumentParser(description="V14-J Experiment Registry")
    parser.add_argument("--pass", dest="pass_number", type=int, default=1, choices=[1, 2])
    parser.add_argument("--no-runtime", action="store_true")
    parser.add_argument("--no-artifact", action="store_true")
    parser.add_argument("--no-pytest", action="store_true")
    args = parser.parse_args()

    from backend.nexus_experiment_registry.campaign import run_experiment_registry_campaign

    status = run_experiment_registry_campaign(
        root=ROOT,
        pass_number=args.pass_number,
        write_artifact=not args.no_artifact,
        write_runtime=not args.no_runtime,
        run_tests=not args.no_pytest,
    )
    print(
        json.dumps(
            {
                "recommendation": status.get("recommendation"),
                "passed": status.get("passed"),
                "pass_number": status.get("pass_number"),
                "scenario_pass_count": status.get("scenario_pass_count"),
                "scenario_total_count": status.get("scenario_total_count"),
                "pytest_passed": status.get("pytest_passed"),
                "secret_leak_count": status.get("secret_leak_count"),
                "silent_cherry_picking": status.get("silent_cherry_picking"),
                "auto_integration": status.get("auto_integration"),
                "oos_consumed": status.get("oos_consumed"),
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
    if status.get("silent_cherry_picking") is not False:
        return 5
    if status.get("auto_integration") is not False:
        return 6
    return 0 if status.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
