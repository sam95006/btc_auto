#!/usr/bin/env python3
"""Dry-run runner for NEXUS_QUALIFICATION_CONTROL_PLANE_V10.

Blocked-only control infrastructure. Does not execute Candidate Freeze,
Replay, Walk-forward, Risk Review, OOS reservation, Demo eligibility,
strategy selection/promotion, or any exchange write.
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

from backend.nexus_autonomy.qualification_control_plane_v10 import (
    run_qualification_control_plane_dry_run,
    write_immutable_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualification control plane V10 dry-run (blocked-only)")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-artifacts", action="store_true", default=True)
    parser.add_argument("--no-write-artifacts", action="store_true")
    args = parser.parse_args()

    summary = run_qualification_control_plane_dry_run()
    artifacts: dict[str, str] = {}
    if args.write_artifacts and not args.no_write_artifacts:
        paths = write_immutable_artifacts(summary, root=args.root)
        artifacts = {k: str(v) for k, v in paths.items()}

    out = {
        "schema": summary["schema"],
        "qualification_status": summary["qualification_status"],
        "control_plane_status": summary["control_plane_status"],
        "all_stages_blocked": summary["all_stages_blocked"],
        "Founder_authorization_present": summary["Founder_authorization_present"],
        "formal_walk_forward_executed": summary["formal_walk_forward_executed"],
        "oos_reservation_created": summary["oos_reservation_created"],
        "oos_executed": summary["oos_executed"],
        "strategy_selected": summary["strategy_selected"],
        "strategy_promoted": summary["strategy_promoted"],
        "demo_order_count": summary["demo_order_count"],
        "stages": summary["stages"],
        "artifacts": artifacts,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
