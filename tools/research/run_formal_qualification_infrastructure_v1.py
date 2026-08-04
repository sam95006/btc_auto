#!/usr/bin/env python3
"""Dry-run runner for NEXUS_FORMAL_QUALIFICATION_INFRASTRUCTURE_V1.

Synthetic fixtures only. Does not execute Walk-forward, OOS, Demo, or promotion.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_autonomy.formal_qualification_infrastructure_v1 import (
    run_infrastructure_dry_run,
    write_immutable_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Formal qualification infrastructure V1 dry-run")
    parser.add_argument("--as-of-ms", type=int, default=1_700_000_000_000)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-artifacts", action="store_true", default=True)
    parser.add_argument("--no-write-artifacts", action="store_true")
    args = parser.parse_args()

    summary = run_infrastructure_dry_run(as_of_ms=args.as_of_ms)
    artifacts: dict[str, str] = {}
    if args.write_artifacts and not args.no_write_artifacts:
        paths = write_immutable_artifacts(summary, root=args.root)
        artifacts = {k: str(v) for k, v in paths.items()}

    out = {
        "schema": summary["schema"],
        "status": summary["status"],
        "Qualification_Infrastructure_status": summary["Qualification_Infrastructure_status"],
        "all_stages_blocked": summary["all_stages_blocked"],
        "formal_walk_forward_executed": summary["formal_walk_forward_executed"],
        "oos_executed": summary["oos_executed"],
        "selected_strategy": summary["selected_strategy"],
        "artifacts": artifacts,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
