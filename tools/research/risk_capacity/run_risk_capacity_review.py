#!/usr/bin/env python3
"""Runner for V15-H Risk and Capacity Review Engine.

Synthetic development fixtures only. No OOS, formal WF, Demo, qualification,
or strategy promotion. AI cannot override deterministic results.
Does not write *_status.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_risk_capacity import (
    build_campaign_summary,
    run_adversarial_review,
    run_risk_capacity_review,
    write_immutable_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="V15-H risk/capacity review engine")
    parser.add_argument("--pass-id", type=int, default=2, choices=(1, 2))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-write-artifacts", action="store_true")
    args = parser.parse_args()

    report = run_risk_capacity_review(pass_id=args.pass_id)
    adversarial = run_adversarial_review(report)
    summary = build_campaign_summary(report, adversarial, root=args.root)

    artifacts: dict[str, str] = {}
    if not args.no_write_artifacts:
        paths = write_immutable_artifacts(report, adversarial, root=args.root)
        artifacts = {k: str(v) for k, v in paths.items()}
        # Hard ban: never write runtime *_status.json
        for p in paths.values():
            if p.name.endswith("_status.json") or p.name == "status.json":
                raise SystemExit(f"STATUS_JSON_ARTIFACT_BANNED:{p.name}")

    out = {
        "schema": summary["schema"],
        "result": summary["result"],
        "pass": summary["pass"],
        "pass_id": args.pass_id,
        "candidate_count": summary["candidate_count"],
        "scenario_point_count": summary["scenario_point_count"],
        "review_dimensions": summary["review_dimensions"],
        "cost_destroyed_count": summary["cost_destroyed_count"],
        "fragile_to_execution_count": summary["fragile_to_execution_count"],
        "capacity_limited_count": summary["capacity_limited_count"],
        "concentration_blocked_count": summary["concentration_blocked_count"],
        "drawdown_unsafe_count": summary["drawdown_unsafe_count"],
        "liquidation_unsafe_count": summary["liquidation_unsafe_count"],
        "data_quality_blocked_count": summary["data_quality_blocked_count"],
        "qualification_ready_count": summary["qualification_ready_count"],
        "strategy_promoted_count": summary["strategy_promoted_count"],
        "ai_override_applied_count": summary["ai_override_applied_count"],
        "ai_override_attempted_count": summary["ai_override_attempted_count"],
        "canonical_cost_authority": summary["canonical_cost_authority"],
        "canonical_cost_formula_mutated": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "auto_integrate_attempted": False,
        "status_json_written": False,
        "adversarial_pass_ok": summary["adversarial_pass_ok"],
        "artifacts": artifacts,
    }
    print(json.dumps(out, indent=2))
    return 0 if adversarial.get("pass_ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
