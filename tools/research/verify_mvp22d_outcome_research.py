#!/usr/bin/env python3
"""Verify MVP-22D outcome tracker modules + synthetic state machine."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_JS = ROOT / "tools" / "research" / "mvp22d_outcome_synthetic_test.mjs"


def main() -> int:
    print("NEXUS MVP-22D anomaly outcome research verification")
    issues: list[str] = []
    for rel in (
        "frontend/src/market/anomalyOutcomeStore.ts",
        "frontend/src/market/anomalyOutcomeAggregation.ts",
        "frontend/src/market/anomalyOutcomeConfig.ts",
        "frontend/src/pages/AnomalyOutcomesPage.tsx",
    ):
        if not (ROOT / rel).is_file():
            issues.append(f"missing:{rel}")

    store = (ROOT / "frontend/src/market/anomalyOutcomeStore.ts").read_text(encoding="utf-8")
    for needle in ("ensureTracking", "PENDING", "COMPLETE", "MISSED", "STALE", "OUTCOME_TIMESTAMP_TOLERANCE_MS"):
        if needle not in store:
            issues.append(f"store_missing:{needle}")

    cfg = (ROOT / "frontend/src/market/anomalyOutcomeConfig.ts").read_text(encoding="utf-8")
    for w in ('"5m"', '"15m"', '"30m"', '"60m"'):
        if w not in cfg:
            issues.append(f"window_missing:{w}")

    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    if 'path="/anomaly-outcomes"' not in app:
        issues.append("route_missing")

    if TEST_JS.is_file():
        proc = subprocess.run(
            ["node", str(TEST_JS)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        print(proc.stdout.strip())
        if proc.returncode != 0:
            issues.append("synthetic_test_failed")
            if proc.stderr:
                print(proc.stderr.strip())

    if issues:
        print(f"FAIL: {len(issues)} issue(s)")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("PASS: outcome windows + lifecycle + synthetic tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
