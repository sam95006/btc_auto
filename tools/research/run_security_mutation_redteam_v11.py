#!/usr/bin/env python3
"""Run NEXUS V11 Security Mutation Red Team and write immutable artifacts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)


def main() -> int:
    from backend.nexus_autonomy.security_mutation_v11.redteam import run_security_mutation_redteam

    status = run_security_mutation_redteam(write_artifact=True, root=ROOT)
    print(
        json.dumps(
            {
                "recommendation": status.get("recommendation"),
                "passed": status.get("passed"),
                "mutation_killed_count": status.get("mutation_killed_count"),
                "mutation_survivor_count": status.get("mutation_survivor_count"),
                "mutation_unresolved_blocker_count": status.get("mutation_unresolved_blocker_count"),
                "mutation_total": status.get("mutation_total"),
                "scenario_pass_count": status.get("scenario_pass_count"),
                "scenario_total_count": status.get("scenario_total_count"),
                "exchange_write_attempt_count": status.get("exchange_write_attempt_count"),
                "secret_leak_count": status.get("secret_leak_count"),
                "mainnet_client_created_count": status.get("mainnet_client_created_count"),
                "critical_findings": status.get("critical_findings"),
                "high_findings": status.get("high_findings"),
                "unresolved_blockers": status.get("unresolved_blockers"),
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
