#!/usr/bin/env python3
"""Run V16 Moat Adversarial Red Team (three passes) and write evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_moat_adversarial_redteam_v16.redteam import (  # noqa: E402
    run_moat_redteam,
    write_coordinator_evidence,
    write_immutable_artifacts,
)


def main() -> int:
    report = run_moat_redteam()
    art = write_immutable_artifacts(report)
    ev = write_coordinator_evidence(report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "recommendation": report["recommendation"],
                "commit": report.get("commit"),
                "survivor_count": len(report["survivors"]),
                "critical_open_count": report["critical_open_count"],
                "high_open_count": report["high_open_count"],
                "blocker_count": len(report["blockers"]),
                "artifacts": str(art),
                "evidence": str(ev),
            },
            indent=2,
        )
    )
    # BLOCKED with only EXPLICITLY_BLOCKED survivors (hard bans) is an acceptable close.
    # FAIL on open Critical/High or PLATFORM_BLOCKED / harness bugs.
    if report["status"] == "PASS":
        return 0
    if (
        report["status"] == "BLOCKED"
        and report["critical_open_count"] == 0
        and report["high_open_count"] == 0
        and report["evaluation"].get("platform_blocked_count", 0) == 0
        and report["evaluation"].get("harness_bug_count", 0) == 0
        and all(s.get("disposition") == "EXPLICITLY_BLOCKED" for s in report["survivors"])
        and all(s.get("attack_blocked") for s in report["survivors"])
    ):
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
