#!/usr/bin/env python3
"""Runner for V13-C Cost-Aware Strategy Discovery Factory V3.

Synthetic development fixtures only. No OOS, formal WF, Demo, or qualification.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_strategy_discovery_factory_v3 import (
    build_status_payload,
    run_adversarial_review,
    run_discovery_factory,
    write_immutable_artifacts,
    write_runtime_status,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="V13-C strategy discovery factory V3")
    parser.add_argument("--pass-id", type=int, default=2, choices=(1, 2))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=Path(r"D:\NEXUS_RUNTIME"),
    )
    parser.add_argument("--no-write-artifacts", action="store_true")
    args = parser.parse_args()

    report = run_discovery_factory(pass_id=args.pass_id)
    adversarial = run_adversarial_review(report)
    summary = build_status_payload(report, adversarial, root=args.root)

    artifacts: dict[str, str] = {}
    if not args.no_write_artifacts:
        paths = write_immutable_artifacts(report, adversarial, root=args.root)
        artifacts = {k: str(v) for k, v in paths.items()}
        runtime_path = write_runtime_status(summary, runtime_root=args.runtime_root)
        artifacts["runtime_status"] = str(runtime_path)

    out = {
        "schema": summary["schema"],
        "status": summary["status"],
        "pass": summary["pass"],
        "pass_id": args.pass_id,
        "mechanism_family_count": summary["mechanism_family_count"],
        "candidate_configuration_count": summary["candidate_configuration_count"],
        "development_promising_count": summary["development_promising_count"],
        "cost_destroyed_count": summary["cost_destroyed_count"],
        "rejected_count": summary["rejected_count"],
        "qualification_ready_count": summary["qualification_ready_count"],
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "adversarial_pass_ok": summary["adversarial_pass_ok"],
        "artifacts": artifacts,
    }
    print(json.dumps(out, indent=2))
    return 0 if adversarial.get("pass_ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
