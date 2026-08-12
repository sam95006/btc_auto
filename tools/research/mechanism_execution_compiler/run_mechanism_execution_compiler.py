#!/usr/bin/env python3
"""Runner for V15-B Mechanism Execution Compiler.

Synthetic development fixtures only. No OOS, formal WF, Demo, qualification, or auto-integrate.
TWO PASSES required. Does NOT write *_status.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_mechanism_execution_compiler import (  # noqa: E402
    build_summary_payload,
    run_adversarial_review,
    run_compiler_campaign,
    write_immutable_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="V15-B Mechanism Execution Compiler")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-write-artifacts", action="store_true")
    args = parser.parse_args()

    # TWO PASSES
    report_p1 = run_compiler_campaign(pass_id=1)
    adv_p1 = run_adversarial_review(report_p1, pass_name="pass_1")

    report_p2 = run_compiler_campaign(pass_id=2)
    adv_p2 = run_adversarial_review(report_p2, pass_name="pass_2")

    report = report_p2
    adversarial_passes = [adv_p1, adv_p2]
    summary = build_summary_payload(report, adversarial_passes, root=args.root)

    artifacts: dict[str, str] = {}
    if not args.no_write_artifacts:
        paths = write_immutable_artifacts(report, adversarial_passes, root=args.root)
        artifacts = {k: str(v) for k, v in paths.items()}
        # Explicit hard ban: never write runtime *_status.json
        status_candidates = [
            Path(r"D:\NEXUS_RUNTIME") / "v15_b_status.json",
            args.root / "v15_b_status.json",
        ]
        for p in status_candidates:
            if p.exists():
                raise RuntimeError(f"status_json_must_not_exist:{p}")

    out = {
        "schema": summary["schema"],
        "status": summary["status"],
        "pass": summary["pass"],
        "pass_1_ok": summary["pass_1_ok"],
        "pass_2_ok": summary["pass_2_ok"],
        "mechanism_executor_count": summary["mechanism_executor_count"],
        "qualification_ready_count": summary["qualification_ready_count"],
        "edge_claim_count": summary["edge_claim_count"],
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "auto_integrate": False,
        "adversarial_remaining_count": summary["adversarial_remaining_count"],
        "critical_remaining": summary["critical_remaining"],
        "high_remaining": summary["high_remaining"],
        "campaign_digest": summary["campaign_digest"],
        "status_json_written": False,
        "artifacts": artifacts,
        "lane_head": summary["lane_head"],
        "blockers": summary["blockers"],
    }
    print(json.dumps(out, indent=2))
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
