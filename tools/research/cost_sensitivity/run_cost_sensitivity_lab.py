#!/usr/bin/env python3
"""Runner for V14-E Cost and Execution Sensitivity Lab.

Synthetic development fixtures only. No OOS, formal WF, Demo, or qualification.
Consumes canonical cost authority — does not mutate CostBridge formulas.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# tools/research/cost_sensitivity/<script> → worktree root is parents[3]
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_cost_sensitivity import (
    build_status_payload,
    run_adversarial_review,
    run_cost_sensitivity_lab,
    write_immutable_artifacts,
    write_runtime_status,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="V14-E cost/execution sensitivity lab")
    parser.add_argument("--pass-id", type=int, default=2, choices=(1, 2))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=Path(r"D:\NEXUS_RUNTIME"),
    )
    parser.add_argument("--no-write-artifacts", action="store_true")
    args = parser.parse_args()

    report = run_cost_sensitivity_lab(pass_id=args.pass_id)
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
        "candidate_count": summary["candidate_count"],
        "scenario_point_count": summary["scenario_point_count"],
        "cost_destroyed_count": summary["cost_destroyed_count"],
        "fragile_to_execution_count": summary["fragile_to_execution_count"],
        "capacity_limited_count": summary["capacity_limited_count"],
        "qualification_ready_count": summary["qualification_ready_count"],
        "canonical_cost_authority": summary["canonical_cost_authority"],
        "canonical_cost_formula_mutated": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "auto_integrate_attempted": False,
        "adversarial_pass_ok": summary["adversarial_pass_ok"],
        "artifacts": artifacts,
    }
    print(json.dumps(out, indent=2))
    return 0 if adversarial.get("pass_ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
