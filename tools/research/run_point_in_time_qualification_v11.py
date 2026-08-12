#!/usr/bin/env python3
"""Run Founder V11 point-in-time qualification infrastructure dry-run.

Synthetic fixtures only. Does not select strategy, execute real Walk-forward,
consume real OOS, run Demo, or promote.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_qualification.pit_v11 import (
    run_point_in_time_qualification_dry_run,
    write_immutable_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Founder V11 PIT qualification dry-run (blocked-only)")
    parser.add_argument("--as-of-ms", type=int, default=1_700_000_000_000)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-artifacts", action="store_true", default=True)
    parser.add_argument("--no-write-artifacts", action="store_true")
    args = parser.parse_args()

    summary = run_point_in_time_qualification_dry_run(as_of_ms=args.as_of_ms)
    artifacts: dict[str, str] = {}
    if args.write_artifacts and not args.no_write_artifacts:
        paths = write_immutable_artifacts(summary, root=args.root)
        artifacts = {k: str(v) for k, v in paths.items()}

    out = {
        "schema": summary["schema"],
        "status": summary["status"],
        "all_stages_blocked_ready": summary["all_stages_blocked_ready"],
        "formal_walk_forward_executed": summary["formal_walk_forward_executed"],
        "oos_reservation_created": summary["oos_reservation_created"],
        "oos_downloaded": summary["oos_downloaded"],
        "oos_executed": summary["oos_executed"],
        "oos_consumed": summary["oos_consumed"],
        "demo_order_count": summary["demo_order_count"],
        "selected_strategy": summary["selected_strategy"],
        "strategy_promoted": summary["strategy_promoted"],
        "artifacts": artifacts,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
